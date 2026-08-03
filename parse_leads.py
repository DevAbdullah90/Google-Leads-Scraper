import ast

with open(r"C:\Users\hp\.local\share\opencode\tool-output\tool_fbca108aa0019L37IsprUVCrh7", "r", encoding="utf-8") as f:
    content = f.read()

data = ast.literal_eval(content)

leads = []
for i, row in enumerate(data[1:], start=2):
    if len(row) >= 3 and row[2] and row[2].strip() != '':
        status = row[9] if len(row) > 9 else ''
        if not status or status.strip() == '':
            leads.append({
                'row': i,
                'name': row[0],
                'phone': row[1],
                'email': row[2],
                'website': row[3],
                'category': row[4],
                'rating': row[5],
                'reviews': row[6],
                'address': row[7],
                'maps_url': row[8]
            })

print(f"Found {len(leads)} unsent leads with email addresses:\n")
for idx, l in enumerate(leads[:25], 1):
    print(f"{idx}. {l['name']} | {l['email']} | Rating: {l['rating']} | Reviews: {l['reviews']}")
    print(f"   Category: {l['category']} | Website: {l['website']}")
    print()
