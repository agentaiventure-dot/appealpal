"""Fictional denial letters used by the fake and the demo. Names, plans and numbers are placeholders."""
CLAIM_DENIAL = """Example Health Plan
Date: 2026-08-20
Member: Alex Example    Member ID: EXAMPLE-MEMBER-0001    Claim number: EXAMPLE-CLAIM-7781

Dear Alex Example,

We have reviewed the claim for the MRI of the lumbar spine performed on 2026-08-02. We are unable to approve payment for this service.
Reason for this decision: The service was not medically necessary because conservative treatment was not documented for at least six weeks before imaging.

You have the right to appeal this decision. Your appeal must be received within 180 days of the date of this letter.
To appeal, send a written request to Example Health Plan, Appeals Department, PO Box 0000, Example City, or call the number on your member card.
If our decision is upheld after the internal appeal, you may request an independent external review.

Sincerely,
Example Health Plan
"""

PRIOR_AUTH_DENIAL = """Example Care Insurance
Date: 2026-08-28
Member: Jordan Sample    Reference: EXAMPLE-PA-3302

Your request for prior authorization of physical therapy (12 visits) has been denied.
Reason: The number of visits requested exceeds the plan limit of 8 visits per calendar year without a documented functional improvement report.
You may file an appeal within 60 days of receiving this notice by submitting the appeal form on the member portal.
"""

BENEFIT_DENIAL_DATED = """Example Vision & Dental Benefits
Date: 2026-08-15
Member: Riley Sample    Reference: EXAMPLE-BEN-4410

Your request for coverage of orthodontic treatment (braces) for your dependent has been denied.
Reason: Orthodontic treatment for dependents is a benefit exclusion under your plan's Schedule of Benefits, section 4.2.

You have the right to appeal. Your appeal must be received by 2026-10-30.
To appeal, mail a written request to Example Vision & Dental Benefits, Appeals Unit, PO Box 1111, Example City.
"""

NO_DEADLINE_DENIAL = """Example Wellness Plan
Date: 2026-08-10
Member: Casey Sample    Reference: EXAMPLE-BEN-9002

Your request for reimbursement of a gym membership under the wellness benefit has been denied.
Reason: The wellness benefit only covers facilities on the approved list, and the submitted facility is not on that list.

If you disagree with this decision, please contact Member Services to discuss your options.
"""

# Registry used by the web UI's "Load sample" buttons and by demo mode's letter-recognition check.
# "marker" is a short substring unique to each letter (its reference number), used to tell a
# recognized sample from arbitrary pasted text without calling the model.
SAMPLES = [
    {"id": "claim_denial", "label": "Claim denial: MRI not medically necessary (180 days from letter date)",
     "marker": "EXAMPLE-CLAIM-7781", "text": CLAIM_DENIAL},
    {"id": "prior_auth", "label": "Prior authorization denial: visit limit exceeded (60 days from letter date)",
     "marker": "EXAMPLE-PA-3302", "text": PRIOR_AUTH_DENIAL},
    {"id": "benefit_denial_dated", "label": "Benefit denial: orthodontic exclusion (explicit appeal-by date)",
     "marker": "EXAMPLE-BEN-4410", "text": BENEFIT_DENIAL_DATED},
    {"id": "no_deadline", "label": "Benefit denial: gym reimbursement (no stated deadline)",
     "marker": "EXAMPLE-BEN-9002", "text": NO_DEADLINE_DENIAL},
]
