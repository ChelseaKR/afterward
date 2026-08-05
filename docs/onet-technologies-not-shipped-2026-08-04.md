# O*NET software lists: investigated, built, and not shipped

2026-08-04. `onet.py` parses a `software_skills` table into `Technology` records (name,
category, and O*NET's "Hot" and "In Demand" flags). It was wired into `build.py`, backfilled
across all 670 occupations, and then removed. This note exists so the next person does not
repeat the work to reach the same answer.

## Why it looked promising

"What software will I be expected to know?" is a concrete question a training decision turns
on, and the table is one batch request rather than a call per occupation — cheap enough to
sit inside an ordinary build, unlike the Spanish records.

## What the data actually contains

Across the 600 occupations with software rows:

| Product | Occupations listing it |
| --- | --- |
| Microsoft Excel | 543 (90%) |
| Microsoft Office software | 521 (86%) |
| Microsoft Outlook | 395 (65%) |
| Microsoft Word | 387 (64%) |
| Microsoft PowerPoint | 348 (58%) |

The top four for Pharmacy Technicians were Excel, Office, Outlook and PowerPoint. True, and
it tells a reader nothing about being a pharmacy technician.

Two further problems:

- **The order carries no information.** `parse_technologies` ranks by the Hot and In Demand
  flags, but 4,217 of 5,513 entries (76%) are flagged Hot, so ties dominate and ties keep
  source order, which is alphabetical. That is why Registered Nurses led with "Apache Spark"
  ahead of Epic Systems.
- **The flags do not discriminate.** A label applied to three-quarters of entries cannot
  separate them.

## Two rankings tried, both rejected

**By rarity, at product level.** Pharmacy Technicians improved to pharmacy management and drug
compatibility software. But rarest-first surfaces the most obscure vendor products: Heavy
Truck Drivers got "Fog Line Software Truckn Pro" and "ddlsoftware.com drivers daily log
program DDL"; Carpenters got "Wilhelm Publishing Threshold". Ranking for obscurity is a
different noise, not less of it.

**By rarity, at category level.** Better for some, wrong for others. Registered Nurses came
out as "Categorization or classification software, Time accounting software, Human resources
software, Business intelligence and data analysis software" — four true statements that
describe nursing to nobody.

## The decision

Not shipped. No ranking tested produces a section that reliably tells a reader something
true *and* useful about the work, and a page that publishes noise in the shape of insight is
the failure this project is built to avoid. Absence is the honest output when the data does
not support the claim, which is the same rule applied to suppressed wages and unreported
outcomes everywhere else on the site.

## What would change the answer

An importance or frequency rating per occupation-software pair, which O*NET publishes for
tasks but not here. With that, "the software this work actually centres on" becomes a claim
the data can support. Rarity is a proxy for it and, as measured above, not a good one.
