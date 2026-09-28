# TPA Member Management — User Guide

## 1. Purpose

The TPA workspace is available under **Portal → TPA Member Management**. It is designed for policy-scoped member enrollment and endorsement operations while reusing GLIS tickets for SLA, approval, assignment, notification and audit workflow.

Portal URL: `/portal/tpa/`

User guide URL: `/portal/tpa/guide/`

## 2. Who can see the TPA menu?

The sidebar menu is shown only when the signed-in user is authorized through at least one of these paths:

- superuser access;
- a TPA Django permission such as `tpa.view_tpa_dashboard`, `tpa.create_enrollment`, `tpa.create_endorsement`, `tpa.approve_endorsement`, `tpa.process_endorsement` or `tpa.configure_tpa`;
- an active `PolicyAccess` row with `can_view=True`;
- an existing TPA transaction requested by that user.

The same authorization is enforced in the TPA views, so manually entering a TPA URL does not bypass the sidebar rule.

## 3. Administrator setup

Before operational users start:

1. Create the Sponsor/Corporate organization.
2. Create the Insurance Company.
3. Create the Policy and set:
   - policy number and name;
   - start and expiry dates;
   - policy status;
   - currency;
   - allowed backdating days;
   - STP enabled/disabled;
   - premium calculation enabled/disabled.
4. Create Benefit Plans for the policy.
5. Configure annual premium, sum insured and premium method for each plan.
6. Create `PolicyAccess` records for users who should see or act on the policy.
7. Assign the required TPA permissions through Django users/groups.

### Main TPA permissions

| Permission | Purpose |
|---|---|
| `tpa.view_tpa_dashboard` | Open the TPA workspace |
| `tpa.create_enrollment` | Create enrollment transactions |
| `tpa.create_endorsement` | Create endorsement transactions |
| `tpa.terminate_member` | Terminate members |
| `tpa.delete_member` | Delete/void members |
| `tpa.cancel_policy` | Cancel policies |
| `tpa.approve_endorsement` | Approval authority |
| `tpa.process_endorsement` | TPA processing authority |
| `tpa.bypass_validation` | Bypass eligible validation rules |
| `tpa.override_premium` | Override premium where implemented |
| `tpa.view_sensitive_member_data` | View sensitive member fields |
| `tpa.view_ai_source_data` | View AI source/extraction data |
| `tpa.configure_tpa` | Configure the TPA module |
| `tpa.export_tpa_data` | Export TPA information |

Policy-level access still limits which policies and transactions a non-superuser can see.

## 4. Dashboard

Open **TPA Member Management** from the portal sidebar.

The dashboard currently shows:

- Active Sponsors
- Active Policies
- Active Members
- Open Transactions
- Needs Information
- Pending Approval
- STP Rate
- Recent Transactions

Recent Transactions includes the TPA reference, GLIS ticket, sponsor, policy, transaction type, source, validation score, STP eligibility and status.

## 5. Create an endorsement

If your account has create authority:

1. Select **New Endorsement**.
2. Select a policy available to your account.
3. Choose the transaction type:
   - New Policy Enrollment
   - Member Addition
   - Member Termination
   - Member Deletion / Void
   - Policy Cancellation
4. Enter the effective date.
5. Enter remarks if required.
6. Save the transaction.
7. Add member rows manually or upload a **CSV/XLSX** spreadsheet.
8. Review row-level validation, premium impact, success/error KPIs and the quality/error charts.
9. Submit the draft.

Submission now creates/links the GLIS operational ticket **and immediately runs deterministic validation**.

For New Policy Enrollment and Member Addition, the member intake expects First Name, Last Name, DOB, Gender, Relationship and Benefit Plan. Employee No., Civil/National ID and Passport are supported identifiers. Spreadsheet headers such as **Full Name**, **DOB**, **Gender**, **Relationship**, **Plan**, **Employee No.**, **Civil ID** and **Passport** are recognized.

If blocking errors exist, the transaction moves to **Validation Failed**. Correct/remove the affected rows and use **Run Validation** again. If all rows pass, GLIS evaluates STP and approval requirements.

## 6. Transaction statuses

| Status | Meaning |
|---|---|
| Draft | Saved but not submitted |
| Extracting | Document/AI extraction in progress |
| Pending Validation | Waiting for deterministic validation |
| Needs Information | Missing/corrected information required |
| Validation Failed | One or more blocking rules failed |
| Pending Approval | Waiting for approval |
| Approved | Approved for processing |
| Auto Approved | Rules allowed straight-through approval |
| Processing | Operational processing in progress |
| Processed | Completed |
| Rejected | Rejected |
| Failed | Processing failed |
| Cancelled | Transaction cancelled |

## 7. Premium calculation

Premium calculation is deterministic. Supported plan configuration methods are:

- `FULL`
- `LUMP_SUM`
- `PARTIAL`
- `PRORATA`

Financial values are normalized to Python `Decimal` and rounded to three decimal places. The calculation result and basis are stored as a snapshot for auditability.

## 8. STP and validation

The current service layer contains deterministic validation and STP eligibility checks. Examples of STP blockers include:

- policy STP disabled;
- validation bypass used;
- member-action validation errors;
- insufficient AI extraction confidence;
- a linked ticket still waiting for approval.

AI extraction can assist with interpretation, but eligibility, pricing, validation, STP and approval decisions remain deterministic.

## 9. AI/document configuration

The shared GLIS AI layer contains:

- AI provider configuration;
- text/vision capability flags;
- extraction profiles;
- training examples;
- source-document records;
- canonical member JSON normalization.

Structured spreadsheet upload is now exposed in the transaction workspace. Full OCR/vision processing of PDF, passport/ID images and other unstructured documents remains a separate AI intake workflow; do not treat that part as complete until the configured provider pipeline has been tested end-to-end.

## 10. Email intake

The TPA data layer can register inbound email metadata including:

- provider;
- provider message ID;
- sender and recipient;
- subject;
- received time;
- email body;
- attachment metadata;
- processing state;
- linked transaction.

Duplicate provider message IDs are prevented.

Automatic mailbox polling and full attachment-to-transaction processing are **foundation components at this stage**, not yet a complete end-user portal workflow.

## 11. Troubleshooting

### TPA menu is not visible

Ask an administrator to check either:

- the user has a suitable TPA permission; or
- the user has an active `PolicyAccess` record with `can_view=True`.

### New Endorsement button is not visible

The user needs either:

- `tpa.create_enrollment`;
- `tpa.create_endorsement`;
- `tpa.configure_tpa`; or
- policy access with `can_create_enrollment=True` or `can_create_endorsement=True`.

### No policies are available

Confirm that an active `PolicyAccess` record exists for the user and policy. Superusers and users with `tpa.configure_tpa` can see all policies.

### Premium calculation error

Check that annual premium and premium configuration values are numeric. The service normalizes configured values to `Decimal` before calculation.

## 12. Approval and processing

After validation succeeds:

- if the policy is STP-enabled and there are no STP blockers, the transaction becomes **Auto Approved**;
- if the linked GLIS ticket has a configured approval workflow, the transaction waits in **Pending Approval** until that approval completes;
- if no ticket approval workflow applies and STP is not available, a user with `tpa.approve_endorsement` or policy-level `can_approve` can approve from the TPA transaction;
- after **Approved** or **Auto Approved**, a user with `tpa.process_endorsement` or policy-level `can_process` selects **Process Transaction**.

For member additions/enrollments, processing creates the Member and active MemberPolicyEnrollment records. Termination/deletion actions update the matching active enrollment. Policy Cancellation cancels the policy and its active enrollments.

## 13. Recommended operational sequence

**Configure organization → configure policy → configure benefit plans → grant permissions/policy access → create transaction → add/upload members → submit & validate → correct errors if any → STP/approval → process → complete/audit through linked GLIS ticket.**
