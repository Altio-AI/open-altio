# Route families: how each value is placed

Each value is one way FDA's data says how a drug was given: a word from the route field of an adverse event report, a dose form from a report, a word found in a reported drug name, or a route name on an FDA drug label. Place each value in every family that a drug given that way could belong to. The families exist to match a report with the FDA label for the same form of the drug, so the question for each value is: which kinds of product could a report or label with this value be about?

The families follow WHO's administration routes (oral, parenteral, rectal, nasal, vaginal, inhalation, sublingual or buccal, transdermal), plus forms WHO gives no doses for:

- **by_mouth**: swallowed, into the stomach (including through a stomach tube).
- **under_tongue**: absorbed through the lining of the mouth (sublingual, buccal, oromucosal).
- **injected**: by injection, infusion or implant into the body.
- **inhaled**: breathed into the lungs.
- **nasal**: into the nose.
- **rectal**: into the rectum.
- **vaginal**: into the vagina.
- **transdermal**: a patch or system through the skin, for an effect in the body.
- **skin**: on the skin, for a local effect.
- **eye**: on or into the eye.
- **ear**: into the ear.
- **other**: a real way of giving a drug that fits none of the above (for example into the bladder, or a dialysis fluid).

Rules:

1. List every family that is plausible for a real product given that way, even a rare one. Leave a family out only when it is not plausible.
2. List exactly one family only when no other is plausible.
3. List no family when the value says nothing about how the drug was given ("unknown", "other", "not specified").
4. Judge the value as written. Do not drop a family because it is less common than another.
5. Give a one-line reason whenever you list more than one family, or the value is unusual.
