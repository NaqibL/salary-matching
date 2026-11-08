/**
 * Public findings and release notes (SGSAL-029). Hand-written; newest first.
 *
 * Rules (from the product review, 2026-11-08):
 * - Each entry fits a phone screen: a date, a plain-sentence headline, one paragraph,
 *   at most three figures, one link to the technical record.
 * - Every number carries its as-of date. No live totals here; the dashboard owns those.
 * - Reposting and agencies are described as counts and definitions, never as intent.
 * - Aggregate findings only; no company is named in editorial copy.
 */

export const CHANGELOG_URL = 'https://github.com/NaqibL/salary-matching/blob/master/CHANGELOG.md'

export interface Figure {
  value: string
  label: string
  asOf: string
}

export interface FindingEntry {
  slug: string
  date: string // display form, e.g. "8 Nov 2026"
  kind: 'finding' | 'fixed' | 'new'
  headline: string
  body: string[]
  figures?: Figure[]
  changelogAnchor?: string
}

export const FINDINGS: FindingEntry[] = [
  {
    slug: 'dashboard-v3',
    date: '8 Nov 2026',
    kind: 'new',
    headline: 'The Dashboard now answers four questions in one scroll.',
    body: [
      'How is the market this week, what does my kind of job pay and how fast is it being posted, which skills are asked for, and how much of what I see is the same ad posted again. Six headline figures carry their scope ("open today", "first seen in the last 7 days"), a job-types table replaces five charts, and a "Posted before" section shows repeats as shares by job type and as a count of how often one ad text is posted. The skills trend chart and the list of most-reposted ads are gone: the first said little, the second was one restaurant template ad.',
      'On the Companies page the recruitment-agency checkbox became a three-way switch: direct employers, recruitment agencies, all. Companies are ordered by distinct ads, so one ad text posted under many listings no longer tops the list, and a "Posted before" column shows the repeat share of each company.',
    ],
    figures: [
      { value: '37%', label: 'of live ads repeat an earlier ad text', asOf: '8 Nov 2026' },
      { value: '38% · 36%', label: 'repeat share for direct employers and for recruitment agencies', asOf: '8 Nov 2026' },
      { value: '29 days', label: 'median time an ad stayed up (ads closed in the last 30 days)', asOf: '8 Nov 2026' },
    ],
    changelogAnchor: 'sgsal-030-dashboard-and-companies-v3',
  },
  {
    slug: 'open-roles-first',
    date: '8 Nov 2026',
    kind: 'fixed',
    headline: 'The salary checker now shows open roles first.',
    body: [
      'Until today the similar-roles cards were chosen purely by how closely an ad matched your description. Because we keep every ad posted since March 2026, closed ads outnumber open ones about ten to one, so most cards were for jobs that had already closed. The pay range was always built from the full history on purpose, and still is, so the numbers you saw before today have not changed. Only the cards changed: they now put open roles first and say how many are open.',
      'We found this after an outside review and a round of test runs on 8 November, which also prompted the agency labels below.',
    ],
    figures: [
      { value: '59 of 98', label: 'similar ads open for a sample Data Analyst check', asOf: '8 Nov 2026' },
      { value: '0 of 20', label: 'cards that were open before the fix, same check', asOf: '8 Nov 2026' },
    ],
    changelogAnchor: 'sgsal-027-checker-shows-open-roles-first',
  },
  {
    slug: 'recruitment-agencies-labelled',
    date: '8 Nov 2026',
    kind: 'new',
    headline: 'Recruitment agencies are now labelled.',
    body: [
      'A company gets a "Recruitment agency" tag when its ACRA registration lists it as an employment agency (SSIC 78), or when it has a recruitment-style name and its registration is not a public body. The tag is a fact about registration, not a judgement. It exists because one role is often advertised by several agencies at once, and because an agency\'s advertised pay range is harder to read than an employer\'s.',
      'Fixed along the way: an earlier rule based on how many kinds of jobs a company posts had tagged universities and research institutes as agencies. It has been replaced by the registration-based rule above, which never tags government bodies, universities or hospitals.',
    ],
    figures: [
      { value: '301 of 1,002', label: 'companies with 10+ openings that carry the label', asOf: '8 Nov 2026' },
      { value: '15 of 15', label: 'largest posting accounts that are agencies', asOf: '8 Nov 2026' },
    ],
    changelogAnchor: 'sgsal-028-companies-registry-and-agency-label',
  },
  {
    slug: 'reposts',
    date: '8 Nov 2026',
    kind: 'finding',
    headline: 'Nearly half of all ads are word-for-word reposts.',
    body: [
      'We now recognise an ad by its text rather than by its listing number. The same text posted again counts once in the pay range, and its history shows on the card: "Posted 6 times since Apr 2026", "Same ad under 3 company names", or "Also posted directly by the employer" when the hiring company posted it themselves. Reposting is allowed on MyCareersFuture; it can mean ongoing hiring, high turnover, or an agency re-running a client role.',
    ],
    figures: [
      { value: '716,225', label: 'postings tracked since Mar 2026', asOf: '8 Nov 2026' },
      { value: '45%', label: 'of those repeated an earlier ad word for word (same title and description)', asOf: '8 Nov 2026' },
      { value: '5,753', label: 'ad texts that appeared under two or more company names', asOf: '8 Nov 2026' },
    ],
    changelogAnchor: 'sgsal-024-posting-history-and-one-vector-per-ad',
  },
  {
    slug: 'companies-page',
    date: '8 Nov 2026',
    kind: 'new',
    headline: 'The Companies page answers "who is hiring for my kind of job, and what do they pay?"',
    body: [
      'Pick a job type and the page lists the employers hiring for it, how many openings each has, what they mainly hire for, and the median advertised monthly salary for that job type at that company. Agencies are hidden by default and one switch brings them back. Each company page shows its registered industry, how often its ads are reposted compared with a typical company, and the ads it has posted most.',
    ],
    figures: [{ value: '1,002', label: 'companies with 10 or more live openings', asOf: '8 Nov 2026' }],
    changelogAnchor: 'sgsal-026-companies-explorer',
  },
  {
    slug: 'hot-jobs',
    date: '1 Jul 2026',
    kind: 'new',
    headline: 'Hot Jobs: roles advertising well above their peers.',
    body: [
      'A daily list of live roles whose advertised pay sits clearly above similar roles. It is a starting point, not a verdict: a high posted range can also mean a hard-to-fill role or an agency estimate.',
    ],
    changelogAnchor: 'sgsal-019-hot-jobs',
  },
  {
    slug: 'methodology-june-2026',
    date: 'Jun 2026',
    kind: 'fixed',
    headline: 'Why your result may have shifted: how we read a salary range.',
    body: [
      'Three changes in June. The headline figure became the middle value (median) of similar ads, with the quarter marks either side shown for context. Each ad counts as the midpoint of its advertised range, and ads like "$3,000 to $8,000", where the top is more than double the bottom, are left out because they tell you nothing. All figures are monthly base salary in SGD; posted ranges tend to run 10 to 20 percent above what is actually offered, so the result says so.',
      'The matching model was also retrained on Singapore job ads so that, for example, a BI Analyst ad no longer counts as evidence for a Data Engineer salary.',
    ],
    figures: [{ value: '85% to 87.5%', label: 'of test ads matched to the right job type, before and after retraining', asOf: 'Jun 2026' }],
    changelogAnchor: 'june-2026-methodology-and-matching-model',
  },
  {
    slug: 'launch',
    date: '31 May 2026',
    kind: 'new',
    headline: 'Lowball launched publicly.',
    body: [
      'Paste a job ad, optionally your offer, and see where it sits against live Singapore listings. Built by one developer; the code is public. A security review was run before launch and everything it found was fixed. The site is free and has no account wall.',
    ],
    changelogAnchor: 'may-2026-public-launch',
  },
]

/** Short definitions for the terms the site uses. Shown under the entries. */
export const GLOSSARY: Array<{ term: string; definition: string }> = [
  {
    term: 'Live jobs',
    definition: 'Listings that were still open on MyCareersFuture or Careers@Gov at the last daily crawl.',
  },
  {
    term: 'Postings tracked',
    definition: 'Every listing we have seen since March 2026, open or closed. The pay range on the checker is built from this history, so it is not swayed by whichever ads happen to be open this week.',
  },
  {
    term: 'Median advertised salary',
    definition:
      'The middle value of the advertised monthly base salaries, each ad counted as the midpoint of its range. Advertised, not paid: posted ranges tend to run 10 to 20 percent above actual offers.',
  },
  {
    term: 'Match',
    definition:
      'How closely an ad\'s text matches the description you pasted, from a model trained on Singapore job ads. 90% is a very close match; below about 55% the roles differ noticeably.',
  },
  {
    term: 'Posted before',
    definition:
      'Live ads whose exact text was posted earlier, under any company name. Shown as a share on the Dashboard and per company as "1 in 4" next to the typical company figure.',
  },
  {
    term: 'Recruitment agency',
    definition:
      'A company whose ACRA registration lists it as an employment agency (SSIC 78), or one with a recruitment-style name whose registration is not a public body. Government bodies, universities and hospitals are never tagged.',
  },
]
