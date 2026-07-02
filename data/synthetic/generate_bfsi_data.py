"""Generate a realistic synthetic BFSI dataset for the omnichannel CX data layer.

Writes a multi-sheet workbook to ``data/synthetic/bfsi_generated.xlsx`` (NOT the
live ``data/bfsi.xlsx`` the running app/tests read today). Review the output,
then a follow-up change will update the Neo4j loader to read this new shape
and cut ``data/bfsi.xlsx`` over to it.

Run:
    python data/synthetic/generate_bfsi_data.py
"""

from __future__ import annotations

import random
import string
from datetime import date, timedelta
from pathlib import Path

import openpyxl
from faker import Faker

SEED = 20260701
TODAY = date(2026, 7, 1)

OUTPUT_PATH = Path(__file__).resolve().parent / "bfsi_generated.xlsx"

# The dataset is scoped to exactly these 5 real name/phone/email triples —
# the user is testing with only these customers, so every sheet's data stays
# consecutive/grouped instead of scattered among unrelated synthetic rows.
# Every other demographic field for these rows is still generated.
PINNED_CUSTOMERS = [
    {"name": "Sayantini Sarkar", "mobile": "7890864700", "email": "sayantini.s.55@gmail.com"},
    {"name": "Sireesha", "mobile": "9398314492", "email": "s.sireesha28092004@gmail.com"},
    {"name": "Digvijay Yadav", "mobile": "7700920746", "email": "digvijayyadav48@gmail.com"},
    {"name": "Hirithi Nandha", "mobile": "9150697784", "email": "hirithi.nandha@gmail.com"},
    {"name": "Fathima Devasahayam", "mobile": "7538870992", "email": "fathimawork511@gmail.com"},
]

fake = Faker("en_IN")
Faker.seed(SEED)
rng = random.Random(SEED)

OCCUPATIONS = [
    "Salaried - Private",
    "Salaried - Government",
    "Self-Employed Professional",
    "Business Owner",
    "Retired",
    "Homemaker",
]
GENDERS = ["Male", "Female", "Other"]
INCOME_BUCKETS = ["Below 5L", "5L-10L", "10L-25L", "25L-50L", "50L+"]
STATES = [
    "Maharashtra", "Delhi", "Karnataka", "Tamil Nadu", "Telangana", "Gujarat",
    "West Bengal", "Rajasthan", "Uttar Pradesh", "Kerala", "Madhya Pradesh", "Punjab",
]
CITY_BY_STATE = {
    "Maharashtra": ["Mumbai", "Pune", "Nagpur"],
    "Delhi": ["New Delhi"],
    "Karnataka": ["Bangalore", "Mysore"],
    "Tamil Nadu": ["Chennai", "Coimbatore"],
    "Telangana": ["Hyderabad"],
    "Gujarat": ["Ahmedabad", "Surat", "Vadodara"],
    "West Bengal": ["Kolkata"],
    "Rajasthan": ["Jaipur"],
    "Uttar Pradesh": ["Lucknow", "Kanpur"],
    "Kerala": ["Kochi", "Thiruvananthapuram"],
    "Madhya Pradesh": ["Bhopal", "Indore"],
    "Punjab": ["Ludhiana", "Amritsar"],
}
BANKS = [
    ("HDFC Bank", "HDFC0"),
    ("ICICI Bank", "ICIC0"),
    ("State Bank of India", "SBIN0"),
    ("Axis Bank", "UTIB0"),
    ("Kotak Mahindra Bank", "KKBK0"),
]
CARD_NETWORKS = ["Visa", "Mastercard", "RuPay"]
CARD_VARIANTS = ["Classic", "Gold", "Platinum", "Signature"]
LOAN_TYPES = {
    "Personal Loan": None,
    "Home Loan": "Property",
    "Auto Loan": "Vehicle",
    "Education Loan": None,
    "Loan Against Property": "Property",
}
POLICY_TYPES = ["Health", "Life", "Term Insurance", "Auto", "Home Insurance"]
TXN_CHANNELS = ["UPI", "NEFT", "IMPS", "ATM", "POS", "NetBanking"]
CHARGE_TYPES = ["MinBalanceNonMaintenance", "AMB", "ENACH_BounceCharge", "LateFee", "AnnualFee"]

_seq_counters: dict[str, int] = {}


def next_id(prefix: str, width: int = 8, start: int = 10001) -> str:
    """Sequential, zero-padded, prefixed ID — looks like a real bank reference number."""
    _seq_counters[prefix] = _seq_counters.get(prefix, start - 1) + 1
    return f"{prefix}{_seq_counters[prefix]:0{width}d}"


def make_pan() -> str:
    letters_a = "".join(rng.choices(string.ascii_uppercase, k=5))
    digits = "".join(rng.choices(string.digits, k=4))
    letter_b = rng.choice(string.ascii_uppercase)
    return f"{letters_a}{digits}{letter_b}"


def make_aadhar_masked() -> str:
    last4 = "".join(rng.choices(string.digits, k=4))
    return f"XXXX-XXXX-{last4}"


def random_date(start: date, end: date) -> date:
    span = (end - start).days
    if span <= 0:
        return start
    return start + timedelta(days=rng.randint(0, span))


def iso(d: date) -> str:
    return d.isoformat()


# ── Customers ────────────────────────────────────────────────────────────────

def generate_customers() -> list[dict]:
    customers = []
    for pinned in PINNED_CUSTOMERS:
        crn = next_id("CRN")
        state = rng.choice(STATES)
        city = rng.choice(CITY_BY_STATE[state])
        occupation = rng.choice(OCCUPATIONS)
        age = rng.randint(23, 65) if occupation != "Retired" else rng.randint(60, 78)
        account_opening = random_date(date(2015, 1, 1), date(2025, 12, 1))
        mobile_changed = random_date(account_opening, TODAY) if rng.random() < 0.3 else None
        email_changed = random_date(account_opening, TODAY) if rng.random() < 0.2 else None

        customers.append({
            "CRN": crn,
            "Name": pinned["name"],
            "Age": age,
            "Gender": rng.choice(GENDERS),
            "Occupation": occupation,
            "City": city,
            "State": state,
            "IncomeLevelApprox": rng.choice(INCOME_BUCKETS),
            "Mobile1": pinned["mobile"],
            "Email1": pinned["email"],
            "PAN": make_pan(),
            "Aadhar": make_aadhar_masked(),
            "AlternateMobile": fake.msisdn()[-10:] if rng.random() < 0.5 else "",
            "AlternateEmail": fake.email() if rng.random() < 0.4 else "",
            "MobileLastChangedDate": iso(mobile_changed) if mobile_changed else "",
            "EmailLastChangedDate": iso(email_changed) if email_changed else "",
            "AccountOpeningDate": iso(account_opening),
            "VintageMonths": 0,          # backfilled after account_opening is fixed
            "TotalProductHolding": "",   # backfilled once all products are generated
            "Segment": "",               # backfilled from income bucket
            "KYCStatus": rng.choices(
                ["Verified", "Pending", "Rejected"], weights=[75, 20, 5]
            )[0],
        })

    for c in customers:
        opened = date.fromisoformat(c["AccountOpeningDate"])
        c["VintageMonths"] = (TODAY.year - opened.year) * 12 + (TODAY.month - opened.month)
        c["Segment"] = {
            "Below 5L": "Mass",
            "5L-10L": "Mass Affluent",
            "10L-25L": "Affluent",
            "25L-50L": "Affluent",
            "50L+": "HNI",
        }[c["IncomeLevelApprox"]]

    return customers


# ── Accounts ─────────────────────────────────────────────────────────────────

def generate_accounts(customers: list[dict]) -> list[dict]:
    accounts = []
    for c in customers:
        bank_name, bank_code = rng.choice(BANKS)
        branch_city = c["City"]
        ifsc = f"{bank_code}{rng.randint(0, 999999):06d}"
        opened = date.fromisoformat(c["AccountOpeningDate"])

        if c["Occupation"] in ("Salaried - Private", "Salaried - Government"):
            account_type, sub_type, min_balance = "CSA", "Salary", 0
        elif c["Occupation"] in ("Self-Employed Professional", "Business Owner"):
            account_type, sub_type, min_balance = "CA", "Income Tax / GST Filing", 10000
        else:
            account_type, sub_type, min_balance = "SA", "Regular", 3000

        avg_balance = round(min_balance * rng.uniform(0.4, 3.0), 2)
        accounts.append({
            "CRN": c["CRN"],
            "AccountNumber": next_id("4090", width=10, start=100001),
            "AccountCategory": "Deposit",
            "AccountType": account_type,
            "AccountSubType": sub_type,
            "OpeningDate": iso(opened),
            "Status": "Active",
            "Branch": f"{branch_city} - {bank_name}",
            "IFSC": ifsc,
            "AvgMonthlyBalance": avg_balance,
            "MinBalanceRequired": min_balance,
            "Currency": "INR",
        })

        if rng.random() < 0.4:
            accounts.append({
                "CRN": c["CRN"],
                "AccountNumber": next_id("4090", width=10, start=100001),
                "AccountCategory": "Deposit",
                "AccountType": "SA",
                "AccountSubType": "Regular",
                "OpeningDate": iso(random_date(opened, TODAY)),
                "Status": "Active",
                "Branch": f"{branch_city} - {bank_name}",
                "IFSC": ifsc,
                "AvgMonthlyBalance": round(rng.uniform(500, 15000), 2),
                "MinBalanceRequired": 3000,
                "Currency": "INR",
            })

    return accounts


def _casa_accounts_for(customer_crn: str, accounts: list[dict]) -> list[dict]:
    return [a for a in accounts if a["CRN"] == customer_crn]


# ── Credit Cards ─────────────────────────────────────────────────────────────

CREDIT_LIMIT_BY_INCOME = {
    "Below 5L": (30000, 100000),
    "5L-10L": (75000, 200000),
    "10L-25L": (150000, 400000),
    "25L-50L": (300000, 700000),
    "50L+": (500000, 1500000),
}


def generate_credit_cards(customers: list[dict], accounts: list[dict]) -> list[dict]:
    cards = []
    for c in customers:
        if rng.random() >= 0.7:
            continue
        casa = _casa_accounts_for(c["CRN"], accounts)
        account_number = casa[0]["AccountNumber"] if casa else ""
        limit_lo, limit_hi = CREDIT_LIMIT_BY_INCOME[c["IncomeLevelApprox"]]
        credit_limit = rng.randrange(limit_lo, limit_hi, 5000)
        balance_due = round(credit_limit * rng.uniform(0.0, 0.8), 2)
        min_due = round(max(500, balance_due * 0.05), 2)

        dpd = rng.choices([0, 5, 15, 30, 45, 60, 90], weights=[65, 10, 8, 7, 5, 3, 2])[0]
        statement_date = random_date(TODAY - timedelta(days=30), TODAY)
        due_date = statement_date + timedelta(days=20)

        fraud_flag = rng.random() < 0.03
        chargeback_flag = rng.random() < 0.05

        cards.append({
            "CRN": c["CRN"],
            "CardID": next_id("CC", width=8, start=100001),
            "AccountNumber": account_number,
            "CreditLimit": credit_limit,
            "CardNetwork": rng.choice(CARD_NETWORKS),
            "CardVariant": rng.choice(CARD_VARIANTS),
            "BalanceDue": balance_due,
            "MinAmountDue": min_due,
            "TotalAmountDue": balance_due,
            "StatementDate": iso(statement_date),
            "PaymentDueDate": iso(due_date),
            "DPD": dpd,
            "InterestRate": round(rng.uniform(36.0, 42.0), 2),
            "PenaltyDetails": f"Late payment fee Rs.{rng.randint(500, 1500)} applied" if dpd > 0 else "None",
            "RewardPointsBalance": rng.randint(0, 15000),
            "RewardPointsExpiry": iso(TODAY + timedelta(days=rng.randint(60, 720))),
            "ChargebackFlag": chargeback_flag,
            "ChargebackReason": rng.choice(["Faulty product received", "Duplicate merchant charge", "Service not rendered"]) if chargeback_flag else "",
            "FraudFlag": fraud_flag,
            "FraudType": rng.choice(["Card Stolen", "Online Fraud"]) if fraud_flag else "",
        })
    return cards


# ── Loans ────────────────────────────────────────────────────────────────────

LOAN_AMOUNT_RANGE = {
    "Personal Loan": (100000, 1500000),
    "Home Loan": (1500000, 9000000),
    "Auto Loan": (300000, 2000000),
    "Education Loan": (200000, 2500000),
    "Loan Against Property": (500000, 5000000),
}
LOAN_TENURE_MONTHS = {
    "Personal Loan": (12, 60),
    "Home Loan": (120, 360),
    "Auto Loan": (36, 84),
    "Education Loan": (60, 180),
    "Loan Against Property": (60, 180),
}
LOAN_INTEREST_RANGE = {
    "Personal Loan": (11.0, 16.0),
    "Home Loan": (8.0, 9.5),
    "Auto Loan": (9.0, 12.0),
    "Education Loan": (9.0, 12.0),
    "Loan Against Property": (9.0, 13.0),
}


def _dpd_bucket_counts(current_dpd: int) -> tuple[int, int]:
    """Historical 60+/90+ DPD occurrence counts, correlated with current DPD."""
    if current_dpd >= 90:
        return rng.randint(2, 5), rng.randint(1, 3)
    if current_dpd >= 60:
        return rng.randint(1, 3), rng.randint(0, 1)
    if current_dpd >= 30:
        return rng.randint(0, 2), 0
    return (rng.randint(0, 1) if rng.random() < 0.1 else 0), 0


def _make_loan(crn: str, account_number: str) -> dict:
    loan_type = rng.choice(list(LOAN_TYPES.keys()))
    collateral = LOAN_TYPES[loan_type] or "None"
    lo, hi = LOAN_AMOUNT_RANGE[loan_type]
    principal = rng.randrange(lo, hi, 10000)
    tenure_lo, tenure_hi = LOAN_TENURE_MONTHS[loan_type]
    tenure = rng.randrange(tenure_lo, tenure_hi + 1, 6)
    rate = round(rng.uniform(*LOAN_INTEREST_RANGE[loan_type]), 2)

    application_date = random_date(date(2018, 1, 1), TODAY - timedelta(days=30))
    months_elapsed = min(tenure, (TODAY.year - application_date.year) * 12 + (TODAY.month - application_date.month))
    months_elapsed = max(months_elapsed, 1)

    dpd = rng.choices([0, 15, 30, 60, 90], weights=[70, 15, 8, 4, 3])[0]
    times_60, times_90 = _dpd_bucket_counts(dpd)

    emis_paid = max(0, months_elapsed - (1 if dpd > 0 else 0))
    emis_paid = min(emis_paid, tenure)
    emis_pending = max(tenure - emis_paid, 0)

    emi = round((principal / tenure) * (1 + rate / 100 / 2), 2)
    balance_due = round(emi * emis_pending, 2)
    status = "Closed" if emis_pending == 0 else ("NPA" if dpd >= 90 else "Active")

    if status == "Active" and emis_paid == 0:
        next_step = "Disbursement pending"
    elif dpd >= 60:
        next_step = "Loan under collections - follow-up call scheduled"
    elif dpd > 0:
        next_step = "EMI overdue - reminder sent"
    elif status == "Closed":
        next_step = "Loan fully repaid"
    else:
        next_step = "EMI auto-debit scheduled"

    return {
        "CRN": crn,
        "LoanID": next_id("LN", width=6, start=1001),
        "AccountNumber": account_number,
        "LoanType": loan_type,
        "CollateralType": collateral,
        "TenureMonths": tenure,
        "PrincipalAmount": principal,
        "InterestRate": rate,
        "BalanceDue": balance_due,
        "MinAmountDue": emi,
        "TotalAmountDue": balance_due,
        "NextPaymentDueDate": iso(TODAY + timedelta(days=rng.randint(1, 28))),
        "LastUpdatedDate": iso(random_date(TODAY - timedelta(days=25), TODAY)),
        "Status": status,
        "DPD": dpd,
        "Times90PlusDPD": times_90,
        "Times60PlusDPD": times_60,
        "PenaltyDetails": f"Overdue penalty Rs.{rng.randint(300, 2500)} applied" if dpd > 0 else "None",
        "EMIsPaid": emis_paid,
        "EMIsPending": emis_pending,
        "TotalEMIs": tenure,
        "NextStep": next_step,
    }


def generate_loans(customers: list[dict], accounts: list[dict]) -> list[dict]:
    loans = []
    for c in customers:
        casa = _casa_accounts_for(c["CRN"], accounts)
        account_number = casa[0]["AccountNumber"] if casa else ""
        roll = rng.random()
        if roll < 0.45:
            continue
        loans.append(_make_loan(c["CRN"], account_number))
        if roll > 0.9:
            loans.append(_make_loan(c["CRN"], account_number))
    return loans


# ── Fixed Deposits ───────────────────────────────────────────────────────────

def generate_fixed_deposits(customers: list[dict], accounts: list[dict]) -> list[dict]:
    fds = []
    for c in customers:
        if rng.random() >= 0.4:
            continue
        casa = _casa_accounts_for(c["CRN"], accounts)
        account_number = casa[0]["AccountNumber"] if casa else ""
        principal = rng.randrange(50000, 2000000, 10000)
        rate = round(rng.uniform(6.5, 7.5), 2)
        tenure = rng.choice([6, 12, 24, 36, 60])
        booking_date = random_date(date(2020, 1, 1), TODAY)
        maturity_date = booking_date + timedelta(days=tenure * 30)
        maturity_amount = round(principal * (1 + (rate / 100) * (tenure / 12)), 2)
        status = "Matured" if maturity_date < TODAY else "Active"
        if status == "Active" and rng.random() < 0.05:
            status = "PrematureClosed"

        fds.append({
            "CRN": c["CRN"],
            "FDID": next_id("FD", width=6, start=1001),
            "AccountNumber": account_number,
            "PrincipalAmount": principal,
            "InterestRate": rate,
            "TenureMonths": tenure,
            "BookingDate": iso(booking_date),
            "MaturityDate": iso(maturity_date),
            "MaturityAmount": maturity_amount,
            "AutoRenewal": rng.choice(["Y", "N"]),
            "Status": status,
        })
    return fds


# ── Policies & Claims ────────────────────────────────────────────────────────

POLICY_COVERAGE_RANGE = {
    "Health": (300000, 1000000),
    "Life": (2000000, 10000000),
    "Term Insurance": (2000000, 10000000),
    "Auto": (300000, 1500000),
    "Home Insurance": (1000000, 5000000),
}
CLAIMABLE_POLICY_TYPES = {"Health", "Auto", "Home Insurance"}
CLAIM_TYPE_BY_POLICY = {
    "Health": ["Hospitalization", "Day-care Procedure", "Pre-existing Condition"],
    "Auto": ["Minor Damage", "Total Loss", "Theft"],
    "Home Insurance": ["Fire Damage", "Burglary", "Structural Damage"],
}


def generate_policies(customers: list[dict]) -> list[dict]:
    policies = []
    for c in customers:
        # Every customer gets at least one claimable policy (Health/Auto/Home)
        # so claim coverage doesn't depend on chance, plus a second policy
        # (claimable or not) most of the time for variety.
        claimable_type = rng.choice(sorted(CLAIMABLE_POLICY_TYPES))
        chosen_types = [claimable_type]
        if rng.random() < 0.6:
            chosen_types.append(rng.choice([t for t in POLICY_TYPES if t != claimable_type]))

        for policy_type in chosen_types:
            lo, hi = POLICY_COVERAGE_RANGE[policy_type]
            coverage = rng.randrange(lo, hi, 10000)
            frequency = rng.choice(["Annual", "Half-Yearly", "Monthly"])
            premium = round(coverage * rng.uniform(0.01, 0.03) / {"Annual": 1, "Half-Yearly": 2, "Monthly": 12}[frequency], 2)
            start_date = random_date(date(2016, 1, 1), TODAY - timedelta(days=30))
            if policy_type in ("Life", "Term Insurance"):
                maturity_date = start_date + timedelta(days=365 * rng.randint(10, 25))
            else:
                maturity_date = start_date.replace(year=min(start_date.year + rng.randint(1, 3), TODAY.year + 3))
            next_due_days = {"Annual": 365, "Half-Yearly": 182, "Monthly": 30}[frequency]
            status = rng.choices(["Active", "Lapsed"], weights=[92, 8])[0]

            policies.append({
                "CRN": c["CRN"],
                "PolicyID": next_id("POL", width=6, start=1001),
                "PolicyType": policy_type,
                "PremiumAmount": premium,
                "CoverageAmount": coverage,
                "PremiumFrequency": frequency,
                "StartDate": iso(start_date),
                "MaturityDate": iso(maturity_date),
                "NextPremiumDueDate": iso(TODAY + timedelta(days=rng.randint(1, next_due_days))),
                "Status": status,
                "NomineeName": fake.name(),
            })
    return policies


CLAIM_STATUSES = ["Approved", "Rejected", "Under Review", "Processing"]


def generate_claims(policies: list[dict]) -> list[dict]:
    claims = []
    for p in policies:
        if p["PolicyType"] not in CLAIMABLE_POLICY_TYPES:
            continue
        # Every claimable policy gets 2-3 claims with deliberately varied
        # statuses (sampled without replacement) rather than leaving claim
        # coverage to compounding chance.
        num_claims = rng.choice([2, 3])
        statuses = rng.sample(CLAIM_STATUSES, k=num_claims)
        for status in statuses:
            claim_type = rng.choice(CLAIM_TYPE_BY_POLICY[p["PolicyType"]])
            amount_claimed = round(p["CoverageAmount"] * rng.uniform(0.02, 0.4), 2)
            if status == "Approved":
                amount_approved = round(amount_claimed * rng.uniform(0.7, 1.0), 2)
                reason = "Documents verified"
            elif status == "Rejected":
                amount_approved = "N/A"
                reason = rng.choice(["Policy exclusion applies", "Claim filed after coverage lapse"])
            else:
                amount_approved = "N/A"
                reason = "Awaiting supporting documents" if status == "Under Review" else "Assessor visit scheduled"

            claims.append({
                "CRN": p["CRN"],
                "ClaimID": next_id("CLM", width=6, start=1001),
                "PolicyID": p["PolicyID"],
                "ClaimType": claim_type,
                "ClaimStatus": status,
                "LastUpdatedDate": iso(random_date(TODAY - timedelta(days=45), TODAY)),
                "AmountClaimed": amount_claimed,
                "AmountApproved": amount_approved,
                "ReasonForStatus": reason,
            })
    return claims


# ── Transactions ─────────────────────────────────────────────────────────────

CHANNEL_WEIGHTS = {"UPI": 45, "NEFT": 15, "IMPS": 15, "ATM": 12, "POS": 10, "NetBanking": 3}
TRANSFER_STATUS_WEIGHTS = {"Success": 88, "Failed": 5, "Pending": 3, "Debited-Pending-Credit": 4}
NON_TRANSFER_STATUS_WEIGHTS = {"Success": 95, "Failed": 5}
FAILURE_REASONS = {
    "Failed": ["Insufficient balance", "Beneficiary bank server timeout", "Invalid beneficiary details"],
    "Pending": ["Processing at beneficiary bank", "Awaiting bank confirmation"],
    "Debited-Pending-Credit": ["Beneficiary bank delayed crediting - auto-reversal in progress"],
}


def generate_transactions(customers: list[dict], accounts: list[dict]) -> list[dict]:
    txns = []
    forced_edge_case_remaining = 3  # guarantee a few "beneficiary not credited" demo cases
    for c in customers:
        casa = _casa_accounts_for(c["CRN"], accounts)
        if not casa:
            continue
        account_number = casa[0]["AccountNumber"]
        num_txns = rng.randint(10, 20)
        for i in range(num_txns):
            channel = rng.choices(list(CHANNEL_WEIGHTS), weights=list(CHANNEL_WEIGHTS.values()))[0]
            txn_type = rng.choices(["Debit", "Credit"], weights=[70, 30])[0]
            amount = round(rng.uniform(100, 50000), 2)
            txn_date = random_date(TODAY - timedelta(days=180), TODAY)

            is_transfer = channel in ("NEFT", "IMPS", "UPI") and txn_type == "Debit"
            if forced_edge_case_remaining > 0 and i == num_txns - 1:
                channel, txn_type, is_transfer = "UPI", "Debit", True
                status = "Debited-Pending-Credit"
                forced_edge_case_remaining -= 1
            elif is_transfer:
                status = rng.choices(list(TRANSFER_STATUS_WEIGHTS), weights=list(TRANSFER_STATUS_WEIGHTS.values()))[0]
            else:
                status = rng.choices(list(NON_TRANSFER_STATUS_WEIGHTS), weights=list(NON_TRANSFER_STATUS_WEIGHTS.values()))[0]

            beneficiary_name = fake.name() if is_transfer else ""
            beneficiary_account = next_id("4090", width=10, start=900001) if is_transfer else ""

            failure_reason = rng.choice(FAILURE_REASONS[status]) if status != "Success" else ""
            narration = {
                "UPI": f"UPI/{beneficiary_name or fake.company()}/payment",
                "NEFT": f"NEFT transfer to {beneficiary_name}",
                "IMPS": f"IMPS transfer to {beneficiary_name}",
                "ATM": "ATM cash withdrawal",
                "POS": f"POS purchase at {fake.company()}",
                "NetBanking": "NetBanking fund transfer",
            }[channel]

            txns.append({
                "TxnID": next_id("TXN", width=10, start=1000001),
                "CRN": c["CRN"],
                "AccountNumber": account_number,
                "TxnDate": iso(txn_date),
                "Amount": amount,
                "TxnType": txn_type,
                "Channel": channel,
                "BeneficiaryAccount": beneficiary_account,
                "BeneficiaryName": beneficiary_name,
                "Status": status,
                "FailureReason": failure_reason,
                "Narration": narration,
            })
    return txns


# ── Charges & Penalties ──────────────────────────────────────────────────────

def generate_charges(accounts: list[dict], loans: list[dict], cards: list[dict]) -> list[dict]:
    charges = []
    for a in accounts:
        if a["AvgMonthlyBalance"] < a["MinBalanceRequired"]:
            charge_type = rng.choice(["MinBalanceNonMaintenance", "AMB"])
            charges.append({
                "ChargeID": next_id("CHG", width=8, start=100001),
                "CRN": a["CRN"],
                "AccountNumber": a["AccountNumber"],
                "ChargeType": charge_type,
                "Amount": round(rng.uniform(100, 750), 2),
                "ChargeDate": iso(random_date(TODAY - timedelta(days=90), TODAY)),
                "Reason": "Average monthly balance below required minimum",
                "ReversalStatus": rng.choices(["Charged", "Reversed", "Disputed"], weights=[75, 15, 10])[0],
            })

    for loan in loans:
        if loan["DPD"] > 0 and rng.random() < 0.5:
            charges.append({
                "ChargeID": next_id("CHG", width=8, start=100001),
                "CRN": loan["CRN"],
                "AccountNumber": loan["AccountNumber"],
                "ChargeType": "ENACH_BounceCharge",
                "Amount": round(rng.uniform(300, 900), 2),
                "ChargeDate": iso(random_date(TODAY - timedelta(days=60), TODAY)),
                "Reason": "e-NACH auto-debit mandate bounced - insufficient funds",
                "ReversalStatus": rng.choices(["Charged", "Reversed", "Disputed"], weights=[80, 10, 10])[0],
            })

    for card in cards:
        if card["DPD"] > 0:
            charges.append({
                "ChargeID": next_id("CHG", width=8, start=100001),
                "CRN": card["CRN"],
                "AccountNumber": card["AccountNumber"],
                "ChargeType": "LateFee",
                "Amount": round(rng.uniform(500, 1500), 2),
                "ChargeDate": iso(random_date(TODAY - timedelta(days=30), TODAY)),
                "Reason": "Credit card payment overdue",
                "ReversalStatus": rng.choices(["Charged", "Reversed", "Disputed"], weights=[85, 10, 5])[0],
            })
        if rng.random() < 0.3:
            charges.append({
                "ChargeID": next_id("CHG", width=8, start=100001),
                "CRN": card["CRN"],
                "AccountNumber": card["AccountNumber"],
                "ChargeType": "AnnualFee",
                "Amount": round(rng.uniform(500, 3000), 2),
                "ChargeDate": iso(random_date(TODAY - timedelta(days=365), TODAY)),
                "Reason": "Annual card membership fee",
                "ReversalStatus": rng.choices(["Charged", "Reversed"], weights=[90, 10])[0],
            })
    return charges


# ── Interactions (conversation history + resolution memory seed) ───────────
#
# Intent values mirror shared/schemas/intents.py::Intent (read-only reference,
# not imported, to keep this generator standalone). Each closed interaction
# becomes a Neo4j (:Interaction) node; rows marked Verified=Y also seed a
# (:ResolutionMemory) cache entry, matching services/neo4j_service/writer.py's
# update_interaction_resolution() property shape exactly.

INTENT_META = {
    "loan_status": {"urgency": "low", "sentiment": "neutral"},
    "claim_status": {"urgency": "medium", "sentiment": "neutral"},
    "policy_status": {"urgency": "low", "sentiment": "neutral"},
    "card_management": {"urgency": "low", "sentiment": "neutral"},
    "transaction_dispute": {"urgency": "high", "sentiment": "negative"},
    "complaint": {"urgency": "medium", "sentiment": "negative"},
    "kyc_update": {"urgency": "low", "sentiment": "neutral"},
    "general_inquiry": {"urgency": "low", "sentiment": "neutral"},
    "account_balance_inquiry": {"urgency": "low", "sentiment": "neutral"},
}


def _money(v) -> str:
    return f"Rs.{float(v):,.0f}"


def generate_interactions(
    customers: list[dict],
    accounts: list[dict],
    cards: list[dict],
    loans: list[dict],
    policies: list[dict],
    claims: list[dict],
    transactions: list[dict],
    charges: list[dict],
) -> list[dict]:
    interactions = []
    for c in customers:
        crn = c["CRN"]
        candidates: list[tuple[str, str, str, str]] = []  # (intent, message, resolution, product_ref)

        for loan in [l for l in loans if l["CRN"] == crn][:2]:
            candidates.append((
                "loan_status",
                f"What is the status of my {loan['LoanType']} (Loan ID {loan['LoanID']})?",
                f"Your {loan['LoanType']} is currently {loan['Status']}. Outstanding balance is "
                f"{_money(loan['BalanceDue'])} with {loan['EMIsPending']} EMI(s) pending.",
                loan["LoanID"],
            ))

        cust_claims = [cl for cl in claims if cl["CRN"] == crn]
        for claim in cust_claims[:2]:
            candidates.append((
                "claim_status",
                f"Can you update me on my claim {claim['ClaimID']}?",
                f"Your claim {claim['ClaimID']} is currently {claim['ClaimStatus']}. {claim['ReasonForStatus']}.",
                claim["PolicyID"],
            ))

        claimed_policy_ids = {cl["PolicyID"] for cl in cust_claims}
        for policy in [p for p in policies if p["CRN"] == crn]:
            if policy["PolicyID"] in claimed_policy_ids:
                continue
            candidates.append((
                "policy_status",
                f"I want to check the status of my {policy['PolicyType']} policy {policy['PolicyID']}.",
                f"Your {policy['PolicyType']} policy is {policy['Status']}, coverage "
                f"{_money(policy['CoverageAmount'])}, next premium due {policy['NextPremiumDueDate']}.",
                policy["PolicyID"],
            ))

        for card in [cd for cd in cards if cd["CRN"] == crn]:
            candidates.append((
                "card_management",
                f"What is the outstanding balance on my credit card {card['CardID']}?",
                f"Your card outstanding is {_money(card['BalanceDue'])}, minimum due "
                f"{_money(card['MinAmountDue'])} by {card['PaymentDueDate']}.",
                card["CardID"],
            ))

        problem_txns = [t for t in transactions if t["CRN"] == crn and t["Status"] in ("Failed", "Debited-Pending-Credit")]
        for txn in problem_txns[:1]:
            candidates.append((
                "transaction_dispute",
                f"I made a payment of {_money(txn['Amount'])} via {txn['Channel']} but it shows {txn['Status']}. Please help.",
                f"We've raised a trace request for transaction {txn['TxnID']}. {txn['FailureReason']} "
                f"The amount will be auto-reversed within 3-5 business days if not credited.",
                txn["AccountNumber"],
            ))

        cust_charges = [ch for ch in charges if ch["CRN"] == crn]
        for charge in cust_charges[:1]:
            candidates.append((
                "complaint",
                f"I was charged {_money(charge['Amount'])} as {charge['ChargeType']} on my account, please explain.",
                f"The charge was applied because: {charge['Reason']}. "
                + ("It has been reversed as a goodwill gesture." if charge["ReversalStatus"] == "Reversed"
                   else "This charge is valid per account terms and conditions."),
                charge["AccountNumber"],
            ))

        casa = _casa_accounts_for(crn, accounts)
        account_number = casa[0]["AccountNumber"] if casa else "general"
        candidates.append((
            "account_balance_inquiry",
            "Can you tell me my current account balance?",
            f"Your available balance as of today is {_money(casa[0]['AvgMonthlyBalance']) if casa else 'N/A'}.",
            account_number,
        ))
        candidates.append((
            "kyc_update",
            "I recently changed my mobile number, can you update my KYC records?",
            f"Your KYC has been updated and the current status is {c['KYCStatus']}. Please visit the nearest "
            f"branch with ID proof if further verification is required.",
            "general",
        ))
        candidates.append((
            "general_inquiry",
            "What are the current features and charges applicable on my account?",
            "Shared the latest account features and applicable charges for your reference.",
            "general",
        ))

        rng.shuffle(candidates)
        chosen_count = min(len(candidates), rng.randint(3, 5))
        for intent, message, resolution, product_ref in candidates[:chosen_count]:
            created = random_date(TODAY - timedelta(days=120), TODAY - timedelta(days=1))
            updated = created + timedelta(days=rng.choice([0, 0, 1]))
            meta = INTENT_META[intent]
            interactions.append({
                "CRN": crn,
                "ConversationID": next_id("CONV", width=8, start=100001),
                "Channel": rng.choice(["whatsapp", "email"]),
                "MessageText": message,
                "Intent": intent,
                "Urgency": meta["urgency"],
                "Sentiment": meta["sentiment"],
                "Status": "closed",
                "ResolutionText": resolution,
                "ProductRef": product_ref,
                "HandledBy": rng.choices(["AI_GROQ", "HUMAN_SR"], weights=[80, 20])[0],
                "CreatedAt": iso(created),
                "UpdatedAt": iso(updated),
                "Verified": rng.choices(["Y", "N"], weights=[70, 30])[0],
            })
    return interactions


# ── Products catalog (curated, not randomized) ──────────────────────────────

def generate_products_catalog() -> list[dict]:
    rows = [
        ("Loan", "Personal Loan", "Smart Personal Loan",
         "Unsecured loan for personal needs.",
         "Quick approval, flexible tenure (1-5 years), competitive interest rates.",
         "Salaried/Self-employed, Min. income INR 25,000/month, Age 21-60."),
        ("Loan", "Home Loan", "Dream Home Loan",
         "Loan for purchasing or constructing a residential property.",
         "Up to 90% financing, long tenure (up to 30 years), attractive interest rates.",
         "Age 18-70, Stable income, Good credit score."),
        ("Loan", "Auto Loan", "Quick Auto Loan",
         "Loan for new or used vehicle purchase.",
         "Up to 100% on-road financing, tenure up to 7 years.",
         "Age 21-65, Valid driving license, Min. income INR 20,000/month."),
        ("Loan", "Education Loan", "Higher Education Loan",
         "Loan for domestic and overseas higher education.",
         "Moratorium during study period, tenure up to 15 years.",
         "Admission confirmation letter, Co-applicant income proof."),
        ("Loan", "Loan Against Property", "Property Power Loan",
         "Loan against residential or commercial property as collateral.",
         "High loan value, tenure up to 15 years, lower interest than personal loans.",
         "Clear property title, Age 25-65."),
        ("CreditCard", "Classic", "Classic Rewards Card",
         "Entry-level credit card with reward points on everyday spends.",
         "1 point per Rs.100 spent, fuel surcharge waiver.",
         "Min. income INR 3L/year, Age 21-60."),
        ("CreditCard", "Gold", "Gold Cashback Card",
         "Cashback-focused credit card for regular spenders.",
         "5% cashback on utility bills, airport lounge access.",
         "Min. income INR 6L/year, Age 21-60."),
        ("CreditCard", "Platinum", "Platinum Travel Card",
         "Travel-focused premium credit card.",
         "Complimentary travel insurance, air miles conversion.",
         "Min. income INR 10L/year, Age 21-60."),
        ("CreditCard", "Signature", "Signature Elite Card",
         "Super-premium metal credit card with concierge services.",
         "Unlimited lounge access, golf privileges, concierge desk.",
         "Min. income INR 25L/year, invite-only."),
        ("FD", "Regular", "Regular Fixed Deposit",
         "Standard fixed deposit with flexible tenure.",
         "Tenure 6 months to 10 years, quarterly compounding.",
         "Any resident individual."),
        ("FD", "Tax Saver", "Tax Saver Fixed Deposit",
         "5-year lock-in FD eligible for tax deduction under 80C.",
         "Fixed 5-year tenure, tax benefit up to Rs.1.5L.",
         "Indian resident individual, PAN mandatory."),
        ("FD", "Senior Citizen", "Senior Citizen FD",
         "Fixed deposit with preferential rates for senior citizens.",
         "Additional 0.5% interest over regular FD rates.",
         "Age 60+."),
        ("Policy", "Health", "Health Shield Plan",
         "Individual health insurance covering hospitalization expenses.",
         "Cashless treatment at network hospitals, no-claim bonus.",
         "Age 18-65 at entry, pre-policy medical check-up above 45."),
        ("Policy", "Health", "Family Floater Health",
         "Family health insurance covering the whole family under one sum insured.",
         "Covers spouse and children, day-care procedures included.",
         "Proposer age 21-65."),
        ("Policy", "Life", "Term Life Secure",
         "Pure protection term life insurance plan.",
         "High cover at low premium, optional riders.",
         "Age 18-65 at entry, medical underwriting required."),
        ("Policy", "Auto", "Motor Secure Auto Policy",
         "Comprehensive motor insurance for cars and two-wheelers.",
         "Own-damage and third-party cover, cashless garage network.",
         "Valid RC and driving license."),
        ("Policy", "Home Insurance", "Home Suraksha Policy",
         "Home insurance covering structure and contents.",
         "Covers fire, burglary, and natural calamities.",
         "Property ownership proof required."),
        ("SavingsAccount", "CSA", "Salary Advantage Account",
         "Zero-balance corporate salary account.",
         "No minimum balance, free debit card, salary-linked benefits.",
         "Salaried employees with employer tie-up."),
        ("SavingsAccount", "SA", "Regular Savings Account",
         "Standard individual savings account.",
         "Free NetBanking and mobile banking, ATM cash withdrawal.",
         "Any resident individual, Age 18+."),
        ("CurrentAccount", "CA", "Current Account for Business",
         "Current account for businesses and self-employed professionals.",
         "Higher transaction limits, overdraft facility, GST filing support.",
         "Valid business registration / GST certificate."),
    ]
    return [
        {
            "ProductID": next_id("PROD", width=4, start=1),
            "ProductName": name,
            "ProductType": product_type,
            "Category": category,
            "Description": description,
            "KeyFeatures": features,
            "EligibilityCriteria": eligibility,
        }
        for product_type, category, name, description, features, eligibility in rows
    ]


# ── Post-processing: total product holding ──────────────────────────────────

def backfill_total_product_holding(
    customers: list[dict],
    accounts: list[dict],
    cards: list[dict],
    loans: list[dict],
    fds: list[dict],
    policies: list[dict],
) -> None:
    for c in customers:
        crn = c["CRN"]
        holdings = []
        if any(a["CRN"] == crn for a in accounts):
            holdings.append("SavingsAccount" if any(a["CRN"] == crn and a["AccountType"] == "SA" for a in accounts) else "")
            holdings.extend({a["AccountType"] for a in accounts if a["CRN"] == crn})
        if any(x["CRN"] == crn for x in cards):
            holdings.append("CreditCard")
        if any(x["CRN"] == crn for x in loans):
            holdings.append("Loan")
        if any(x["CRN"] == crn for x in fds):
            holdings.append("FixedDeposit")
        if any(x["CRN"] == crn for x in policies):
            holdings.append("Policy")
        holdings = sorted({h for h in holdings if h})
        c["TotalProductHolding"] = ",".join(holdings)


# ── Workbook writer ──────────────────────────────────────────────────────────

def write_workbook(sheets: dict[str, list[dict]], output_path: Path) -> None:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for sheet_name, rows in sheets.items():
        ws = wb.create_sheet(title=sheet_name)
        if not rows:
            continue
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            ws.append([row.get(h, "") for h in headers])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)


def main() -> None:
    customers = generate_customers()
    accounts = generate_accounts(customers)
    cards = generate_credit_cards(customers, accounts)
    loans = generate_loans(customers, accounts)
    fds = generate_fixed_deposits(customers, accounts)
    policies = generate_policies(customers)
    claims = generate_claims(policies)
    transactions = generate_transactions(customers, accounts)
    charges = generate_charges(accounts, loans, cards)
    interactions = generate_interactions(customers, accounts, cards, loans, policies, claims, transactions, charges)
    products = generate_products_catalog()

    backfill_total_product_holding(customers, accounts, cards, loans, fds, policies)

    sheets = {
        "Customer_Demographics": customers,
        "Accounts": accounts,
        "Credit_Cards": cards,
        "Loans": loans,
        "Fixed_Deposits": fds,
        "Policies": policies,
        "Claims": claims,
        "Transactions": transactions,
        "Charges_Penalties": charges,
        "Interactions": interactions,
        "Products_Catalog": products,
    }
    write_workbook(sheets, OUTPUT_PATH)

    print(f"Wrote {OUTPUT_PATH}")
    for name, rows in sheets.items():
        print(f"  {name}: {len(rows)} rows")


if __name__ == "__main__":
    main()
