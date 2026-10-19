# Look at the data online

For anyone who wants the data without installing anything.

[open.altioai.com](https://open.altioai.com) serves every Open Altio release in the same explorer you can run on your own machine, plus downloads of every release. Access is free. This page covers applying, what you can do once approved, MedDRA, and the licence.

## Apply

Each person applies for themselves, whether they work for a company, a university, a regulator or a nonprofit, or for nobody.

- **The form asks** who you are, where you work and how you will use the data.
- **You accept** the [Open Altio Data Licence](https://open.altioai.com/licence) for yourself.
- **A person at Altio reads every application** and emails you the decision, with the reason if it is no. Most applications are decided within a day.

Signing in is by a link sent to your email address. There is no password.

## What you can do once approved

- **Explore:** products, reactions, all cases and the case window, with charts, filters and every column marked FDA or Open Altio, as in [the local explorer](explorer.md).
- **Export** what your filters show. A filtered export is always named and described as filtered, so it can never be mistaken for the full data.
- **Download** every release, whole or table by table, as Parquet. Every past release stays downloadable; the explorer shows the latest.
- **Query** the release with read-only SQL, within the limits in [`rules/sql-limits.md`](https://github.com/Altio-AI/open-altio/blob/main/rules/sql-limits.md).
- **Tell us what to improve:** the Improve this button on every page sends your note, the page and the part you pointed at.

## MedDRA

**Reactions are counted and found by their preferred term** in the release's MedDRA version, so a search for Seizure also finds the cases FDA wrote as Convulsion.

- **Without a verified subscription.** open.altioai.com may instead show people without a verified subscription each reaction exactly as FDA wrote it, with the statistics counted that way too. The page then says so where reactions are listed, and verified subscribers keep today's names.
- **The case list always shows FDA's text as written.** An old term written in capitals is shown in MedDRA's spelling with FDA's capitals beside it.
- **Downloads and exports carry FDA's text only.**

MedDRA's own content needs a MedDRA subscription, yours or your organisation's:

- its codes;
- the hierarchy above the preferred term;
- the SMQs;
- a search by any lower level term;
- which preferred term each of FDA's texts reads to, shown beside it in the case list and a case.

**Give your MedDRA ID** when you apply, or later in Settings.

- open.altioai.com checks it with MSSO, MedDRA's maintainer.
- It turns the hierarchy and SMQs on for you once the subscription is verified.
- It checks again as you use it, so access follows the subscription.
- Several people may share their organisation's ID.

## What is kept about you

What you do on the site is logged, including the text of your SQL queries, for the time the [privacy notice](https://open.altioai.com/privacy) states. You can delete your own account in Settings at any time.

## Using what you download

The licence lets you share and adapt the data for any purpose, including commercial use, provided you:

- credit "Open Altio" and the release you used;
- say what you changed;
- pass on the FAERS disclaimer;
- never try to identify a person.

The [licence](https://open.altioai.com/licence) has the full terms.

A release you build yourself from FDA's files is not covered by this licence: it is yours. See [Rebuild from FDA's files](../customise/rebuild.md).
