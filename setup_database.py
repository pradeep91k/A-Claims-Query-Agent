import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "claims_agent.db"
random.seed(42)  # reproducible data across runs


def create_tables(conn):
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS claims (
        claim_id MTEXT PRIMARY KEY,
        member_id TEXT NOT NULL,
        patient_name TEXT NOT NULL,
        service_date TEXT NOT NULL,
        billed_amount REAL NOT NULL,
        status TEXT NOT NULL,
        denial_code TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS eligibility (
        member_id TEXT PRIMARY KEY,
        patient_name TEXT NOT NULL,
        plan_name TEXT NOT NULL,
        eligibility_status TEXT NOT NULL,
        coverage_start TEXT NOT NULL,
        coverage_end TEXT NOT NULL,
        copay REAL NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS denial_codes (
        code TEXT PRIMARY KEY,
        code_type TEXT NOT NULL,
        description TEXT NOT NULL
    )
    """)

    conn.commit()


# Real CARC (Claim Adjustment Reason Codes) and RARC (Remittance Advice Remark Codes)
# Source: standard X12 835 code lists used industry-wide
DENIAL_CODES = [
    ("CARC", "1", "Deductible amount"),
    ("CARC", "2", "Coinsurance amount"),
    ("CARC", "3", "Co-payment amount"),
    ("CARC", "11", "The diagnosis is inconsistent with the procedure"),
    ("CARC", "16", "Claim/service lacks information or has submission/billing error(s)"),
    ("CARC", "18", "Exact duplicate claim/service"),
    ("CARC", "22", "This care may be covered by another payer per coordination of benefits"),
    ("CARC", "27", "Expenses incurred after coverage terminated"),
    ("CARC", "29", "The time limit for filing has expired"),
    ("CARC", "50", "These are non-covered services because this is not deemed a medical necessity"),
    ("CARC", "96", "Non-covered charge(s)"),
    ("CARC", "97", "The benefit for this service is included in the payment/allowance for another service"),
    ("CARC", "109", "Claim/service not covered by this payer/contractor"),
    ("CARC", "197", "Precertification/authorization/notification absent"),
    ("RARC", "N130", "Consult plan benefit documents for limitations or requirements"),
    ("RARC", "N362", "The number of days or units exceeds acceptable maximum"),
    ("RARC", "N657", "This should be billed with the appropriate code for these services"),
    ("RARC", "M51", "Missing/incomplete/invalid procedure code(s)"),
]

PLANS = ["PPO Gold 500", "HMO Silver 750", "EPO Bronze 1000", "PPO Platinum 250"]
STATUSES_ELIGIBILITY = ["Active", "Inactive", "Pending Verification"]
STATUSES_CLAIM = ["Submitted", "In Review", "Approved", "Paid", "Denied"]

FIRST_NAMES = ["James", "Mary", "Robert", "Patricia", "John", "Linda", "Michael", "Barbara",
               "William", "Elizabeth", "David", "Jennifer", "Richard", "Susan", "Joseph", "Karen"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
              "Rodriguez", "Martinez", "Wilson", "Anderson", "Taylor", "Thomas", "Moore", "Jackson"]


def random_date(start_year=2024, end_year=2025):
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta_days = (end - start).days
    return (start + timedelta(days=random.randint(0, delta_days))).strftime("%Y-%m-%d")


def seed_denial_codes(conn):
    cursor = conn.cursor()
    cursor.executemany(
        "INSERT OR REPLACE INTO denial_codes (code, code_type, description) VALUES (?, ?, ?)",
        [(code, code_type, desc) for code_type, code, desc in DENIAL_CODES]
    )
    conn.commit()


def seed_eligibility(conn, n=25):
    """Returns a dict of {member_id: patient_name} so claims can reuse real names."""
    cursor = conn.cursor()
    members = {}
    rows = []
    for i in range(1, n + 1):
        member_id = f"M{1000 + i}"
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        plan = random.choice(PLANS)
        status = random.choices(STATUSES_ELIGIBILITY, weights=[80, 10, 10])[0]
        coverage_start = "2024-01-01"
        coverage_end = random_date(2024, 2024) if status == "Inactive" else "2025-12-31"
        copay = random.choice([15, 25, 30, 40, 50])
        rows.append((member_id, name, plan, status, coverage_start, coverage_end, copay))
        members[member_id] = name

    cursor.executemany(
        "INSERT OR REPLACE INTO eligibility VALUES (?, ?, ?, ?, ?, ?, ?)", rows
    )
    conn.commit()
    return members


def seed_claims(conn, members, n=30):
    cursor = conn.cursor()
    denial_codes_only = [code for _, code, _ in DENIAL_CODES]
    member_ids = list(members.keys())
    rows = []
    for i in range(1, n + 1):
        claim_id = f"CLM{5000 + i}"
        member_id = random.choice(member_ids)
        patient_name = members[member_id]
        service_date = random_date(2024, 2025)
        billed_amount = round(random.uniform(50, 5000), 2)
        status = random.choices(STATUSES_CLAIM, weights=[10, 15, 30, 30, 15])[0]
        denial_code = random.choice(denial_codes_only) if status == "Denied" else None
        rows.append((claim_id, member_id, patient_name, service_date, billed_amount, status, denial_code))

    cursor.executemany(
        "INSERT OR REPLACE INTO claims VALUES (?, ?, ?, ?, ?, ?, ?)", rows
    )
    conn.commit()


def preview(conn):
    """Quick sanity check - prints one sample row from each table."""
    cursor = conn.cursor()
    print("\n--- Sample claim ---")
    print(cursor.execute("SELECT * FROM claims WHERE status='Denied' LIMIT 1").fetchone())
    print("\n--- Sample eligibility record ---")
    print(cursor.execute("SELECT * FROM eligibility LIMIT 1").fetchone())
    print("\n--- Sample denial code ---")
    print(cursor.execute("SELECT * FROM denial_codes LIMIT 1").fetchone())


def main():
    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)
    seed_denial_codes(conn)
    members = seed_eligibility(conn, n=25)
    seed_claims(conn, members, n=30)
    preview(conn)
    conn.close()
    print(f"\nDone. Database created at: {DB_PATH}")
    print("Tables: claims (30 rows), eligibility (25 rows), denial_codes (18 rows)")


if __name__ == "__main__":
    main()
