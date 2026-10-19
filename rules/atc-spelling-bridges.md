---
rule: atc-spelling-bridges
line: Where WHO and our drug dictionary spell a substance differently, such as ciclosporin and cyclosporine, a reviewed list joins them, so it still gets its class.
values:
  mapping: mappings/faers/atc/bridges.csv
enforced_in:
  - src/open_altio/faers/atc/table.py
  - tests/faers/atc/test_table.py
---
# WHO's spellings matched to ours

WHO and the DiAna dictionary mostly write a substance the same way. Where they differ, such as ciclosporin and cyclosporine, a reviewed list joins the two, so the substance still gets its class.

The substances a drug record names come from the DiAna dictionary, which writes international names (INN) in lower case without salts. WHO's index mostly writes the same names, so most substances join WHO's name for them as it stands. Where the two write one substance differently, the reviewed list in `mapping` bridges them: each row is a word as WHO writes it (in lower case), a substance as the dictionary writes it, and why they are the same.

A row adds a spelling, it never replaces one: WHO's own name keeps joining, so a dictionary that writes both `ciclosporin` and `cyclosporine` finds the class either way.

A row's `substance` may be a set of ingredients, sorted and joined with `;`. A row whose word is WHO's whole name for a combination code ("buprenorphine, combinations") joins that code to the substance or set it names, and so does a row whose word is WHO's name for a class (levels 2 to 4) WHO classes some combinations by ("calcium, combinations with vitamin D and/or other drugs"); a class's name stands only for a set, since a single word that is a class's name ("diuretics") is a part of combination names. Where WHO gives a class the name of the one class below it (A12A "CALCIUM", A12AA "Calcium"), the row stands for the deeper class. A row may also name a spelling FDA writes in its own fields rather than the dictionary's (`tozinameran` for the Pfizer-BioNTech Covid-19 vaccine), which only FDA's words on a record find (rule atc-index).

Six kinds of row, each named in its `evidence`:

- **A salt, ester or form.** WHO names `levothyroxine sodium` and `tiotropium bromide`; the dictionary names `levothyroxine` and `tiotropium`.
- **A name.** US names (USAN) the dictionary keeps for an INN (`cyclosporine` for `ciclosporin`), and the dictionary's own names: vitamins by letter (`vitamin d3` for `colecalciferol`), plants and bacteria by genus (`senna spp`).
- **A substance WHO codes only in combinations.** WHO has no code for `sacubitril` alone, only `valsartan and sacubitril`; the row lets the part stand for the dictionary's substance.
- **A class word in a combination name.** WHO names some combinations by a class: `levodopa and decarboxylase inhibitor`, `amoxicillin and beta-lactamase inhibitor`, `valsartan and diuretics`. Each row names one substance the class stands for in a product reported to FAERS (`carbidopa`, `clavulanic acid`, `hydrochlorothiazide`), so `carbidopa;levodopa` finds its combination code. WHO names the hormonal IUD the same way, `plastic IUD with progestogen`, and its row names levonorgestrel, the hormone of Mirena, Kyleena, Skyla and Liletta.
- **A product WHO codes as one.** WHO's name for a combination or a class stands for the dictionary's set of its ingredients (`intrauterine contraceptive device;levonorgestrel` for the hormonal IUD), or for the one part a record names when the product is always the pair (`imipenem` for imipenem and cilastatin).
- **A spelling in FDA's fields.** FDA's active ingredient names the exact product where the dictionary names only a group: `insulin human`, `tozinameran`, `human immunoglobulin g`.

**Why:** without the bridges, the substances reported most often would have no class: levothyroxine alone is in more than half a million cases. Each row was accepted only where the cases it codes were counted on the release and found to be the same substance (`notebooks/faers/09_drug_classes`); a row that codes no case is not kept. Words WHO uses that have no row here stay unjoined rather than guessed.
