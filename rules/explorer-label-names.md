---
rule: explorer-label-names
values:
  product_from: See full prescribing information for
  marks: ["®", "™", "©", "(R)", "(TM)", "TM"]
  capitals_up_to: 3
  small_words: [and, for, of, with, the, in, to]
  shared_word_letters: 4
enforced_in:
  - src/open_altio/explorer/labelnames.py
  - tests/explorer/test_labelnames.py
---
# How the screens name a label

Wherever the screens name the label a flag was read on, they name it by its product, its ingredients and its date, and say that the link opens DailyMed: "Diovan (valsartan) label, 11-Aug-2026, on DailyMed", "Diovan HCT (hydrochlorothiazide and valsartan) label, 13-Feb-2026, on DailyMed". The same words are used on a drug's Statistics tab, in the Label column's tips and in the case window, so two labels a drug's reports were read on can always be told apart.

- **The product.** It is read from the label's own title (`title_T` in `label_candidates_T`), where FDA's Highlights write it after `product_from`: "See full prescribing information for DIOVAN HCT." It is the words after that phrase that are written in capitals, up to the first word with a small letter, a word with no letter or the end of the sentence, with the marks in `marks` taken out (a sign wherever it stands, a mark of letters only as a word of its own). A name written twice in a row is written once.
- **No product, the ingredients alone.** A label whose title has no such sentence (older labels, written before the Highlights), whose words there are not in capitals, or whose name shares a word of `shared_word_letters` letters or more with its ingredients (a generic's "VALSARTAN TABLETS") is named by its ingredients alone: "valsartan label".
- **The ingredients** are RxNorm's names for the label's ingredient or combination (`ingredient_T`), joined with "and".
- **Capitals.** A brand FDA writes in capitals is written in title case: each word with a capital letter first. A word of `capitals_up_to` letters or fewer after the first keeps its capitals, since it is usually an abbreviation (Diovan HCT, Adderall XR); a word in `small_words` is written small (Emend for Injection).
- **Forms only where the labels differ by form.** A label's forms are named only when the labels read for the page (a drug's Statistics tab, or one case) include two set IDs for one RxNorm code, chosen for different route families (rule label-choice): "Hemady (dexamethasone) by-mouth and under-the-tongue label", "dexamethasone injected label". The forms are the route families the label was chosen for, in the words of rule explorer-label-flags. A drug with one label for each code says nothing about forms, even where that label is read for several families: a tablet's label stands for by mouth and under the tongue because FDA's route Oral allows both (rule drug-route), not because there are two labels.
- **The date** is the label's effective date (`effective_date_T`). The link is DailyMed's page for its set ID at the version the flags were read from (`spl_version_T`), not the newest DailyMed holds, so a reader checks a flag against the words it was read from. Its tip says so, and when the labels are checked against DailyMed each day (`checked_at_utc` of rule label-refresh): "The version these flags were read from. Labels are checked against DailyMed every day at <time> UTC; the newest may differ until then.", the time read from that one value There is no second link to the newest version.

**Why:** a label named only by its forms and date ("the by-mouth labels, dated 11-Aug-2026") cannot be told apart from another of the same forms. The product and its ingredients say which label it is; the forms add nothing on a drug with one label per product. Of the 2,493 labels chosen for FAERS 2026Q2, 1,407 name a brand in capitals in the Highlights sentence; the rest are named by their ingredients. 261 of the 2,128 RxNorm codes with a label have different labels for different forms. A name read from the SPL's own product field, not its title, would name every label; it needs a new column in `label_candidates_T`.
