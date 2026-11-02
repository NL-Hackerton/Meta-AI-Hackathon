# Local policy pre-check (`src/adloom/policy.py`, `src/adloom/policy_rules.yaml`)

Sources read on 2026-11-02. This check makes no network call.

## What this is and is not

- It is a **pre-check**: a fixed table of regular expressions run over the ad copy before the owner
  approves. It catches a few common risky phrasings, in Korean and English, and suggests a
  concrete replacement.
- It is **not Meta ad review**. Meta reviews every ad itself. Its review covers the image, video,
  audio, targeting and landing page. Meta can reject an ad this check passes, and Meta may accept
  some phrases this check flags. A clean result here means only that no listed pattern matched.
- Policy flags are always recomputed locally. They are never taken from the model.

Meta's own description of its review, from the
[Introduction to the Advertising Standards](https://transparency.meta.com/policies/ad-standards/):
"When advertisers place an order, each ad is reviewed against our policies." The same page says
the review "may include the specific components of an ad, such as images, video, text and
targeting information, as well as an ad's associated landing page".

## How a rule is applied

Each rule in `policy_rules.yaml` has these fields. The file is JSON, which is a subset of YAML.

| Field | Meaning |
|---|---|
| `id` | Stable rule ID, shown on the review screen as `rule <id>`. |
| `category` | The policy area the rule comes from. |
| `severity` | `block` locks approval until the text changes. `warn` is shown but does not block. |
| `fields` | Field scope: `primary_text`, `headline`, `hook` (`hook:<id>`), `subtitle` (`subtitle:<n>`). |
| `pattern` | Case-insensitive Python regex. |
| `replacement` | Literal text that replaces each match in the suggested rewrite. |
| `policy_url` | The Meta page the rule is based on. |

- `check(fields)` returns one `Flag` per (field, rule) match. The `rewrite` is the field text with
  every match of that rule replaced by `replacement`.
- Subtitles come from the confirmed transcript and cannot be edited after render. A `block` rule
  that matches a subtitle is therefore reported as `warn` there. The fix is to re-record or re-confirm
  the narration.
- `POLICY_DIGEST` is the SHA-256 of the rule file. It is recorded in the approval subject, so
  editing the table changes what an approval covers.
- Every replacement is checked to trigger no rule. Every rule has positive and negative tests in
  `tests/test_policy.py`. The rewrites are a starting point for the owner. They are not always
  grammatical in context.

## False-positive controls

- English patterns use word boundaries (`\b`). They exclude common harmless phrases: "best before",
  "best regards", "do our best", "before and after school", "free of / free from", "no hurry",
  "risk-free trial".
- Korean patterns name the particle or ending they expect, so they don't match inside longer words.
  For example, `최고` is not flagged in `최고급` or `최고기온`, and `1등` is not flagged in `1등급`.
  `1위` is not flagged in `11위`, and `게이` is not flagged in `게이밍`. A personal attribute such as
  `당뇨` is flagged only when it is asked about ("당뇨가 있으신가요?") or attached to the viewer
  ("당신의 …"). A plain mention such as "당뇨 환자를 위한 저당 빵" is not flagged.
- Weight-loss timeframe rules need a loss verb, so "3일 안에 1kg 원두 배송" is not flagged.
- Guarantee rules need an outcome word, so "100% 환불 보장", "Money-back guarantee" and
  "100% 국내산" are not flagged.

## Rules

### Personal attributes (block)

Source: [Privacy Violations and Personal Attributes](https://transparency.meta.com/policies/ad-standards/objectionable-content/privacy-violations-personal-attributes/)

> "ads must not contain content that asserts or implies personal attributes. This includes direct
> or indirect assertions or implications about a person's race, ethnicity, religion, beliefs, age,
> sexual orientation or practices, gender identity, disability, physical or mental health
> (including medical conditions), vulnerable financial status, voting status, membership in a
> trade union, criminal record, or name."

The page's not-allowed examples include "Are you Christian?", "Are you 18 years old?", "Do you have
diabetes?", "Depression getting you down? Get help now." and "Are you bankrupt? Check out our
services." Its allowed examples include "New diabetes treatment available", and it allows
"'you/your' language without a personal attribute".

| id | Catches | Replacement |
|---|---|---|
| `personal_attribute_en` | "Are you / Do you have / Struggling with / Questioning your" + a listed attribute (health, religion, sexuality, gender identity, age such as "18 years old", debt or bankruptcy, criminal record); "<condition> getting you down" | `Made for everyone.` |
| `personal_attribute_ko` | A listed attribute + a question ending (`있으신가요`, `이신가요`, `고민하시나요`, `힘드신가요` …), or `당신의/고객님의` + attribute | `누구나 부담 없이 만나보세요.` |

### Health claims (block)

Source: [Health and Wellness](https://transparency.meta.com/policies/ad-standards/restricted-goods-services/health-wellness/)

> "Claims (including those from health professionals or health organizations) to cure, heal, or
> eliminate any of the following incurable diseases and/or terminal illnesses (exhaustive list):
> Diabetes, Herpes, Thyroid, Psoriasis, Ebola, Cancer, Autism, Alzheimer's, Parkinson's,
> Amyotrophic Lateral Sclerosis (ALS), Human immunodeficiency virus (HIV)"

> "Employ clickbait tactics in a health, weight loss, or weight gain context, such as sensational
> language with exaggerated or extreme claims, or promises of specific outcomes within a set
> timeframe without disclaimers or qualifiers."

> "Contains statements of inferiority about physical appearance (i.e., terms, descriptions, or
> questions that are negative and attack an individual's appearance, specific body parts, or
> hygiene)."

The "no side effects" and `완치` (complete cure) patterns also rest on
[Unacceptable Business Practices](https://transparency.meta.com/policies/ad-standards/fraud-scams/unacceptable-business-practices/):
"Ads can't: Use deceptive or exaggerated claims about health-related benefits of a product or
service".

| id | Catches | Replacement |
|---|---|---|
| `health_cure_claim_en` | "cures / heals / eliminates / reverses / a cure for" + a disease from Meta's list; "no side effects" | `supports everyday wellbeing` |
| `health_cure_claim_ko` | `완치`; `부작용 없음/없는/없어요`; a disease from Meta's list + `치유/낫게/고쳐/없애/극복` | `건강한 일상을 응원해요` |
| `weight_loss_timeframe_en` | "lose / drop / shed <n> kg/lbs in <n> days/weeks/months" | `support a balanced routine` |
| `weight_loss_timeframe_ko` | A timeframe (`2주 만에`, `한 달`, `일주일에`) + `-<n>kg` or `<n>kg 감량/빠져요/뺐어요` | `꾸준한 관리에 도움` |
| `negative_self_image_en` | "ugly / flabby / embarrassing" + a body part; "hate your <body part>"; "tired of being fat" | `feeling good` |
| `negative_self_image_ko` | `뱃살/팔뚝살/군살 …` + `고민/스트레스/때문에`; `못생긴/뚱뚱한/부끄러운` + a body part | `기분 좋은 하루` |

Meta does not list treating or managing symptoms as a violation ("This does not apply to claims
about treating or managing symptoms of these conditions."), so `치료` (treatment) and "manage" are
not flagged.

### Before/after (warn)

Source: [Health and Wellness](https://transparency.meta.com/policies/ad-standards/restricted-goods-services/health-wellness/)

Meta allows before/after content in some cases, so this rule only warns. When targeting people 18
or older, advertisers can run dietary weight-loss ads where "The ad can illustrate people using the
product or the service, and its impact of using it, and clearly indicate the time taken to achieve
noticeable results." They can also run "General cosmetic products, procedures, surgeries depicting
before and after transformation." The warning asks the owner to check the 18+ targeting, the
stated time taken, and whether the product is in a covered category.

| id | Catches | Replacement |
|---|---|---|
| `before_after_en` | "before and after", "before & after", "before/after" (not "before and after school/work/class …") | `customer photo` |
| `before_after_ko` | `비포 애프터`, `전후 비교/사진`, `사용 전 후` | `실제 사용 모습` |

### Guaranteed results (block)

Source: [Unacceptable Business Practices](https://transparency.meta.com/policies/ad-standards/fraud-scams/unacceptable-business-practices/)

> "Ads can't: Use deceptive or exaggerated claims about the success of a product or service to
> mislead people into purchasing or sharing sensitive information"

| id | Catches | Replacement |
|---|---|---|
| `guaranteed_results_en` | "100% guaranteed / effective / success", "guaranteed results / to work / weight loss", "results guaranteed", "works every time" | `carefully made` |
| `guaranteed_results_ko` | `100% 보장`, `무조건 보장/효과/성공/합격`, `효과/결과/성공/합격 (을) 보장`, with the following ending (`하는`, `합니다` …) | `정성을 다하는` |

### Income and financial promises (block)

Source: [Prohibited Commercial Practices (Community Standard)](https://transparency.meta.com/policies/community-standards/prohibited-commercial-practices/).
The ad-standards page [Prohibited Commercial Practices](https://transparency.meta.com/policies/ad-standards/deceptive-content/prohibited-commercial-practices/)
says: "Ads Must Comply with the Community Standard on Prohibited Commercial Practices", which
prohibits practices "such as deceptive pricing, unauthorized endorsements, and guaranteed
investment returns".

> "Offers of investment opportunities where returns on investment are guaranteed or risk-free."

> "Offers of opportunities of unrealistic financial reward for unclear or minimal effort."

> "Loan offers that guarantee approval without any mention of standard approval criteria"

| id | Catches | Replacement |
|---|---|---|
| `income_promise_en` | "guaranteed returns / profits / income / approval", "risk-free investment / returns / trading", "make / earn $<n> a day/week/month", "get rich quick", "double your money" | `clear terms` |
| `income_promise_ko` | `원금/수익(률)/투자금 보장`, `무위험 투자/수익`, `월 <n>만원 수익/보장/벌기`, `일확천금`, `고수익 보장`, `대출 승인 보장` | `조건을 투명하게 안내해요` |

### Unproven superlatives (warn)

Source: [Unacceptable Business Practices](https://transparency.meta.com/policies/ad-standards/fraud-scams/unacceptable-business-practices/)
(same "deceptive or exaggerated claims about the success of a product or service" line).

Meta has no rule that bans the word "best". An unsupported "#1" or "최고" is only an exaggerated
claim when it is not true, and this check cannot know whether it is. So the rule only warns, and
asks the owner to keep the claim only if they can back it up (for example, a named award or a
ranking source).

| id | Catches | Replacement |
|---|---|---|
| `unproven_superlative_en` | "(the) best", "#1", "No. 1", "number one", "world's first / finest / greatest", "unbeatable" | `much-loved` |
| `unproven_superlative_ko` | `최고(의)` (not `최고급/최고가/최고기온` …), `1위`, `1등` (not `1등급`), `넘버원`, `국내/세계/업계 최초/유일` | `자신 있는` |

### Urgency and scarcity (warn)

Source: [Avoid creating negative experiences with your ads](https://www.facebook.com/business/m/one-sheeters/avoid-creating-negative-experiences-with-ads)
(Meta Business). This page is about ad quality, not an Advertising Standards rejection rule:

> "Sensationalism includes using exaggerated headlines or commanding a reaction from people to a
> degree that creates an unexpected experience"

> "If your ads exhibit any of these attributes, their performance may be affected. They may be
> shown to fewer people, and your ads may be disapproved more often."

Meta's Advertising Standards do not name false scarcity directly. A real time-limited offer is
fine, so this rule only warns, and asks the owner to keep the phrase only if it is true.

| id | Catches | Replacement |
|---|---|---|
| `urgency_scarcity_en` | "today only", "last chance", "only <n> left", "selling out fast", "ends tonight", "while supplies last", "act now", "hurry" (not "no hurry") | `during the promotion` |
| `urgency_scarcity_ko` | `오늘만`, `마감 임박`, `품절 임박`, `곧 마감`, `마지막 기회`, `지금 안 사면`, `단 <n>개/명 남/한정` | `행사 기간 내` |

### Misleading price claims (warn)

Source: [Unacceptable Business Practices](https://transparency.meta.com/policies/ad-standards/fraud-scams/unacceptable-business-practices/)
says such violations are often seen in "Misleading schemes that promote free products or
services". The
[Prohibited Commercial Practices Community Standard](https://transparency.meta.com/policies/community-standards/prohibited-commercial-practices/)
lists "Misleading or unreasonable pricing" and "Deceptive subscription practices".

A local check cannot see whether a "free" offer has hidden conditions. It flags the absolute forms
that leave no room for the conditions (`완전 무료`, "totally free", "free forever"), plus
unprovable lowest-price claims. A free offer whose condition is stated next to it, such as
"3만원 이상 무료배송" or "Free delivery over $30", is not flagged.

| id | Catches | Replacement |
|---|---|---|
| `misleading_price_en` | "totally / completely / 100% / absolutely free" (not "free of/from"), "free forever", "no strings attached", "lowest price(s) (guaranteed)", "cheapest" | `good value (see terms)` |
| `misleading_price_ko` | `완전/전부/100%/평생/무조건/조건 없이 무료`, `(역대) 최저가 (보장)`, `최저 가격` | `혜택가(조건 안내 참고)` |

## Known gaps

- The check reads text fields only: primary text, headline, hooks and subtitles. It does not read
  the video, the thumbnail, the CTA, the targeting or the landing page, all of which Meta reviews.
- It does not know the product category. So it cannot apply Meta's category rules, such as 18+
  targeting for weight-loss and cosmetic ads, or prior written permission for dating, gambling
  and cryptocurrency ads.
- Phrasings that are not in the table are not caught: paraphrases, other languages, misspellings.
