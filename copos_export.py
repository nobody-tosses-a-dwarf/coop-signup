"""
CoPOS export: generates the 60-column tab-delimited TXT file
that CoPOS expects for member import.
"""

from datetime import datetime


COPOS_HEADERS = [
    "Member #", "Member Name #1", "Member Name #2", "Street Address",
    "City", "State", "Zip Code", "Phone", "E-Mail",
    "Eligible for Senior Disc?", "Tax Exempt", "Newsletter", "Active",
    "Voting Privileges", "Credit Limit", "Special Order Disc",
    "Basic Member Disc", "Senior Discount", "Working Member Discount",
    "Working Member Discount Expires On", "Employee Discount", "Total Discount",
    "Membership Type", "Date Joined", "Member Due Date", "Paid in Installments",
    "Initial Payment Date", "One Time Sign Up Fee Paid", "Installment Fee Paid",
    "Equity Contract", "Dues Contract",
    "1st Payment Date", "Equity Pd In", "Dues Pd In", "Total 1St Payment",
    "2nd Payment Date", "Equity Pd In", "Dues Pd In", "Total 2nd Payment",
    "3rd Payment Date", "Equity Pd In", "Dues Pd In", "Total 3rd Payment",
    "4th Payment Date", "Equity Pd In", "Dues Pd In", "Total 4th Payment",
    "5th Payment Date", "Equity Pd In", "Dues Pd In", "Total 5th Payment",
    "6th Payment Date", "Equity Pd In", "Dues Pd In", "Total 6th Payment",
    "Total Equity Paid to Date", "Total Dues Paid to Date", "Grand Total Paid in",
    "Date Last Purchased", "Int#"
]


def format_date(iso_date):
    """Convert ISO date to MM/DD/YYYY for CoPOS."""
    if not iso_date:
        return ""
    try:
        d = datetime.fromisoformat(iso_date)
        return d.strftime("%m/%d/%Y")
    except (ValueError, TypeError):
        return ""


def format_currency(amount):
    """Format as decimal with 2 places, no dollar sign."""
    if amount is None or amount == 0:
        return "0.00"
    return f"{amount:.2f}"


def export_members_copos(conn, coop_id):
    """
    Generate CoPOS-compatible tab-delimited export for all members of a co-op.
    Returns the file content as a string.
    """
    members = conn.execute("""
        SELECT m.*, mt.name as type_name, mt.label as type_label,
               mt.equity_amount, mt.dues_amount, mt.signup_fee
        FROM members m
        JOIN membership_types mt ON m.membership_type_id = mt.id
        WHERE m.coop_id = ?
        ORDER BY m.member_number
    """, (coop_id,)).fetchall()

    lines = []
    # Header row
    lines.append("\t".join(COPOS_HEADERS))

    for member in members:
        payments = conn.execute("""
            SELECT * FROM payments
            WHERE member_id = ?
            ORDER BY installment_number
        """, (member["id"],)).fetchall()

        paid_in_installments = "Yes" if member["payment_plan"] == "installment" else "No"

        # Initial payment date = first payment date if paid
        initial_payment_date = ""
        installment_fee_paid = "0.00"
        if payments:
            first_pmt = payments[0]
            if first_pmt["paid"]:
                initial_payment_date = format_date(first_pmt["paid_date"])

        # Build payment columns (6 slots)
        pmt_cols = []
        total_equity_paid = 0.0
        total_dues_paid = 0.0

        for i in range(6):
            if i < len(payments):
                pmt = payments[i]
                eq = pmt["equity_amount"] if pmt["paid"] else 0
                du = pmt["dues_amount"] if pmt["paid"] else 0
                pmt_date = format_date(pmt["paid_date"]) if pmt["paid"] else ""
                total_equity_paid += eq
                total_dues_paid += du
                pmt_cols.extend([
                    pmt_date,
                    format_currency(eq),
                    format_currency(du),
                    format_currency(eq + du)
                ])
            else:
                pmt_cols.extend(["", "0.00", "0.00", "0.00"])

        grand_total = total_equity_paid + total_dues_paid

        # Basic member discount - CoPOS typically wants a percentage
        basic_disc = ""
        senior_disc = ""
        working_disc = ""
        employee_disc = ""
        total_disc = ""

        row = [
            str(member["member_number"]),           # Member #
            member["name_1"],                        # Member Name #1
            member["name_2"] or "",                  # Member Name #2
            member["street_address"],                # Street Address
            member["city"],                          # City
            member["state"],                         # State
            member["zip_code"],                      # Zip Code
            member["phone"],                         # Phone
            member["email"],                         # E-Mail
            "Yes" if member["senior_discount"] else "No",  # Senior Disc
            "Yes" if member["tax_exempt"] else "No", # Tax Exempt
            "Yes" if member["newsletter"] else "No", # Newsletter
            "Yes" if member["active"] else "No",     # Active
            "Yes" if member["voting_privileges"] else "No",  # Voting
            "",                                      # Credit Limit
            "",                                      # Special Order Disc
            basic_disc,                              # Basic Member Disc
            senior_disc,                             # Senior Discount
            working_disc,                            # Working Member Discount
            "",                                      # Working Member Discount Expires
            employee_disc,                           # Employee Discount
            total_disc,                              # Total Discount
            member["type_label"],                    # Membership Type
            format_date(member["date_joined"]),      # Date Joined
            format_date(member["member_due_date"]),  # Member Due Date
            paid_in_installments,                    # Paid in Installments
            initial_payment_date,                    # Initial Payment Date
            format_currency(member["signup_fee"]),   # One Time Sign Up Fee
            installment_fee_paid,                    # Installment Fee Paid
            format_currency(member["equity_amount"]),# Equity Contract
            format_currency(member["dues_amount"]),  # Dues Contract
        ] + pmt_cols + [
            format_currency(total_equity_paid),      # Total Equity Paid to Date
            format_currency(total_dues_paid),        # Total Dues Paid to Date
            format_currency(grand_total),            # Grand Total Paid in
            "",                                      # Date Last Purchased
            ""                                       # Int# (CoPOS internal)
        ]

        lines.append("\t".join(row))

    return "\n".join(lines)
