-- ============================================================
-- Seed reference data: service catalog + reason-code taxonomy.
-- Idempotent via ON CONFLICT (code) so re-running is safe.
-- ============================================================

insert into public.service_type (code, name, description) values
  ('GP_VISIT',         'General Practitioner Visit', 'Primary care consultation'),
  ('SPECIALIST_VISIT', 'Specialist Visit',           'Consultation with a medical specialist'),
  ('PHYSIO',           'Physiotherapy',              'Physical therapy session'),
  ('DENTAL',           'Dental',                     'Dental treatment'),
  ('OPTICAL',          'Optical',                    'Vision / optical services'),
  ('DIAGNOSTIC',       'Diagnostic Test',            'Lab tests and imaging'),
  ('MENTAL_HEALTH',    'Mental Health',              'Mental health consultation or therapy'),
  ('PHARMACY',         'Pharmacy',                   'Prescription medication'),
  ('EMERGENCY',        'Emergency Care',             'Emergency room / urgent care')
on conflict (code) do nothing;

insert into public.reason_code (code, category, default_message) values
  ('NOT_COVERED',                'denial',     'This service is not covered under the policy.'),
  ('POLICY_INACTIVE',            'denial',     'The policy was not active on the service date.'),
  ('SERVICE_DATE_OUT_OF_COVERAGE','denial',    'The service date falls outside the coverage period.'),
  ('ANNUAL_LIMIT_EXCEEDED',      'denial',     'The annual coverage limit for this service has been reached.'),
  ('VISIT_LIMIT_EXCEEDED',       'denial',     'The annual visit limit for this service has been reached.'),
  ('OVER_REVIEW_THRESHOLD',      'review',     'The billed amount exceeds the manual-review threshold.'),
  ('DEDUCTIBLE_APPLIED',         'adjustment', 'Part of the amount was applied to the annual deductible.'),
  ('COPAY_APPLIED',              'adjustment', 'A fixed copay was applied.'),
  ('COINSURANCE_APPLIED',        'adjustment', 'Coinsurance was applied to the covered amount.'),
  ('LIMIT_PARTIALLY_APPLIED',    'adjustment', 'Payable amount was reduced by the remaining annual limit.'),
  ('COVERED_IN_FULL',            'adjustment', 'The service was covered in full.')
on conflict (code) do nothing;
