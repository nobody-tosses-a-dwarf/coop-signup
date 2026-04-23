from datetime import datetime, timedelta
from typing import List, Dict

def generate_copos_export(members: List[Dict], coop: Dict) -> str:
    """
    Generate CoPOS 60-column tab-delimited export file.
    
    Format:
    1. MemberNumber
    2. FirstName
    3. LastName
    4. Address
    5. City
    6. State
    7. Zip
    8. Phone
    9. Email
    10. JoinDate
    11-16. Payment installment slots (date, amount pairs)
    17. EquityContract (total equity amount)
    18. DuesContract (always 0 for Chatham)
    19-58. Other CoPOS fields (mostly blank/calculated)
    59. MemberType
    60. Notes
    """
    
    lines = []
    
    for member in members:
        row = [''] * 60  # Initialize 60 columns
        
        # Basic info (columns 1-9)
        row[0] = str(member['member_number'])
        row[1] = member['first_name']
        row[2] = member['last_name']
        row[3] = member['address']
        row[4] = member['city']
        row[5] = member['state']
        row[6] = member['zip']
        row[7] = member['phone'] or ''
        row[8] = member['email'] or ''
        
        # Join date (column 10)
        if isinstance(member['signed_up_at'], str):
            join_date = datetime.fromisoformat(member['signed_up_at'].replace('Z', '+00:00'))
        else:
            join_date = member['signed_up_at']
        row[9] = join_date.strftime('%m/%d/%Y')
        
        # Payment installments (columns 11-22: 6 slots of date,amount pairs)
        # For quarterly installments, fill in 4 slots
        if member['payment_plan'] == 'installments':
            total_amount = member['total_equity'] + member['signup_fee']
            installment_amount = total_amount / 4
            
            for i in range(4):
                due_date = join_date + timedelta(days=90 * i)
                row[10 + (i * 2)] = due_date.strftime('%m/%d/%Y')  # Date
                row[11 + (i * 2)] = f"{installment_amount:.2f}"  # Amount
        
        # Equity Contract (column 23 - index 22)
        row[22] = f"{member['total_equity']:.2f}"
        
        # Dues Contract (column 24 - index 23) - always 0 for equity-based model
        row[23] = "0.00"
        
        # Member Type (column 59 - index 58)
        row[58] = member.get('membership_type_name', 'Standard')
        
        # Payment Plan Note (column 60 - index 59)
        payment_notes = {
            'full': 'Paid in Full',
            'installments': 'Quarterly Installments',
            'later': 'Pay Later'
        }
        row[59] = payment_notes.get(member['payment_plan'], '')
        
        # Join row with tabs
        lines.append('\t'.join(row))
    
    return '\n'.join(lines)
