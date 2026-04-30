import psycopg, os
conn = psycopg.connect(os.environ['DATABASE_URL'])
slugs = ('wild-onion-market', 'fertile-ground', 'gem-city-market', 'prairie-commons')
conn.execute("DELETE FROM coops WHERE slug = ANY(%s)", (list(slugs),))
conn.commit()
conn.close()
print("Cleaned up demo co-ops.")
