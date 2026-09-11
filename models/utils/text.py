"""Text normalisation and the prescription parsing engine.

Two jobs live here:

1. **Normalisation** used by the OCR agreement scorer, so ``"Tab. Dolo 650mg"``
   and ``"tab dolo 650 mg"`` compare as the same string.
2. **Extraction** used by the FB-03 NER fallback — a curated drug lexicon plus
   regexes for dose and frequency. This is deliberately a real, explainable
   parser rather than a random stub: it is the extractor of record whenever
   medspaCy is not installed, and it is also the cross-check for medspaCy's own
   output in ``services/ner_service.py``.
"""

from __future__ import annotations

import re
from typing import Iterable

# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s./-]")
_PAREN_RE = re.compile(r"\([^)]*\)")


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace and strip the result."""
    return _WS_RE.sub(" ", text or "").strip()


def comparable(text: str) -> str:
    """Canonical form used for character/word error rates.

    Lowercases, drops bracketed asides and punctuation, and collapses
    whitespace so that formatting differences do not inflate the error rate.
    """
    lowered = (text or "").lower()
    lowered = _PAREN_RE.sub(" ", lowered)
    lowered = lowered.replace("\n", " ")
    lowered = _PUNCT_RE.sub(" ", lowered)
    return normalize_whitespace(lowered)


# --------------------------------------------------------------------------
# Lexicons
# --------------------------------------------------------------------------

#: Common generics and Indian market brands. Lowercase; matched on word
#: boundaries so "pan" never matches inside "pantoprazole" or "company".
DRUG_LEXICON: frozenset[str] = frozenset(
    """
    paracetamol acetaminophen ibuprofen aspirin diclofenac naproxen aceclofenac
    tramadol codeine morphine tapentadol etoricoxib celecoxib ketorolac
    metformin glimepiride glibenclamide gliclazide sitagliptin pioglitazone
    dapagliflozin empagliflozin insulin lantus huminsulin mixtard vildagliptin
    atorvastatin rosuvastatin simvastatin pravastatin fenofibrate ezetimibe
    amlodipine nifedipine cilnidipine telmisartan losartan valsartan olmesartan
    ramipril enalapril lisinopril perindopril metoprolol atenolol bisoprolol
    carvedilol nebivolol hydrochlorothiazide furosemide torsemide spironolactone
    clopidogrel ticagrelor prasugrel warfarin rivaroxaban apixaban heparin
    enoxaparin dabigatran
    amoxicillin clavulanate azithromycin clarithromycin erythromycin cefixime
    ceftriaxone cefuroxime cephalexin cefpodoxime ciprofloxacin levofloxacin
    ofloxacin moxifloxacin doxycycline tetracycline minocycline metronidazole
    tinidazole cotrimoxazole sulfamethoxazole trimethoprim nitrofurantoin
    gentamicin amikacin vancomycin linezolid meropenem imipenem ertapenem
    piperacillin tazobactam cloxacillin ampicillin penicillin cefotaxime
    cefazolin fluconazole itraconazole ketoconazole clotrimazole terbinafine
    acyclovir valacyclovir oseltamivir albendazole ivermectin
    hydroxychloroquine chloroquine artemether lumefantrine primaquine
    ondansetron domperidone metoclopramide ranitidine famotidine pantoprazole
    omeprazole esomeprazole rabeprazole lansoprazole sucralfate dicyclomine
    hyoscine loperamide lactulose bisacodyl isabgol
    cetirizine levocetirizine loratadine fexofenadine chlorpheniramine
    diphenhydramine montelukast salbutamol levosalbutamol formoterol budesonide
    beclomethasone fluticasone ipratropium tiotropium deriphyllin aminophylline
    prednisolone prednisone dexamethasone betamethasone hydrocortisone
    methylprednisolone deflazacort
    levothyroxine thyroxine carbimazole methimazole propylthiouracil
    amitriptyline sertraline fluoxetine escitalopram paroxetine mirtazapine
    alprazolam clonazepam diazepam lorazepam etizolam zolpidem
    phenytoin valproate levetiracetam carbamazepine lamotrigine phenobarbitone
    gabapentin pregabalin sumatriptan propranolol flunarizine donepezil
    levodopa carbidopa rasagiline
    allopurinol febuxostat colchicine
    calcium ferrous folic cyanocobalamin cholecalciferol thiamine pyridoxine
    riboflavin ascorbic becosules neurobion shelcal calcimax zincovit supradyn
    limcee
    orlistat tamsulosin finasteride sildenafil tadalafil
    methotrexate azathioprine cyclosporine tacrolimus mycophenolate rituximab
    tamoxifen letrozole imatinib isotretinoin tretinoin
    permethrin mupirocin fusidic povidone lignocaine lidocaine adrenaline
    atropine dopamine dobutamine noradrenaline fentanyl midazolam propofol
    ketamine rocuronium neostigmine naloxone flumazenil
    dextrose sodium potassium magnesium ringer saline mannitol
    dolo crocin calpol combiflam saridon disprin brufen voveran zerodol hifenac
    ultracet glycomet glimestar januvia galvus atorva storvas rosuvas amlopres
    telma losar cardace metolar betaloc concor lasix aldactone clopilet plavix
    brilinta xarelto eliquis mox amoxyclav augmentin azee azithral claribid
    taxim monocef zifi cifran levoflox oflox doxy metrogyl flagyl septran
    nitrofur genticyn vancocin linox meronem pipzo flucon itrasys candid
    zovirax tamiflu albend ivermec lariago coartem emeset vomikind pantocid
    omez razo sucrafil cyclopam buscopan imodium duphalac cremaffin dulcolax
    allerheal alegra avil montair asthalin foracort budecort seretide ventolin
    duolin omnacortil wysolone dexona betnesol thyronorm eltroxin amitone
    serlift nexito feliz alprax rivotril lonazep valparin levipil tegretol
    gabapin pregeb suminat ciplar donep syndopa zyloric febustat colchic folvite
    urimax finast becosule
    """.split()
)

#: Conditions a prescription or discharge note commonly names.
CONDITION_LEXICON: frozenset[str] = frozenset(
    """
    hypertension hypotension diabetes mellitus prediabetes dyslipidemia anaemia
    anemia asthma copd tuberculosis pneumonia bronchitis pharyngitis tonsillitis
    sinusitis otitis influenza dengue malaria typhoid gastroenteritis gastritis
    acid peptic reflux dyspepsia constipation diarrhoea diarrhea colitis
    irritable bowel uti pyelonephritis cystitis nephrolithiasis renal failure
    hepatitis cirrhosis pancreatitis cholecystitis osteoarthritis rheumatoid
    gout migraine epilepsy stroke neuropathy thyroid hypothyroidism
    hyperthyroidism dermatitis eczema psoriasis urticaria conjunctivitis
    cataract glaucoma myocardial infarction angina arrhythmia heart failure
    stroke covid pneumonia sepsis hypoxia dehydration malnutrition obesity
    depression anxiety insomnia fracture sprain dengue fever viral fever
    """.split()
)

_DRUG_TOKENS: tuple[str, ...] = tuple(sorted(DRUG_LEXICON, key=len, reverse=True))


def _boundary_pattern(tokens: Iterable[str]) -> re.Pattern[str]:
    """Word-boundary alternation, longest token first, case-insensitive."""
    ordered = sorted(tokens, key=len, reverse=True)
    body = "|".join(re.escape(token) for token in ordered)
    return re.compile(rf"(?<![A-Za-z0-9])(?:{body})(?![A-Za-z0-9])", re.IGNORECASE)


_DRUG_RE = _boundary_pattern(_DRUG_TOKENS)
_CONDITION_RE = _boundary_pattern(CONDITION_LEXICON)

# --------------------------------------------------------------------------
# Field regexes
# --------------------------------------------------------------------------

_FORM_PREFIX_RE = re.compile(
    r"^\s*(?:tab|tabs|tablet|cap|caps|capsule|syp|syr|syrup|inj|injection|susp|"
    r"suspension|drops?|oint|ointment|gel|cream|spray|sachet|powder|sol|soln|"
    r"solution|lotion|supp|suppository)\b\.?\s*",
    re.IGNORECASE,
)

_DOSAGE_RE = re.compile(
    r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*"
    r"(mg|mcg|µg|ug|g|gm|gram|grams|ml|cc|iu|units?|%|puffs?|drops?|tsp|tbsp)"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)

#: Bare strengths such as the "650" in "Dolo 650" — recorded as a dose without
#: a unit so downstream pricing and interaction checks still see the number.
_BARE_STRENGTH_RE = re.compile(r"(?<![A-Za-z0-9])(\d{2,4})(?![A-Za-z0-9])")

_FREQ_ABBR: dict[str, str] = {
    "od": "once daily",
    "qd": "once daily",
    "bd": "twice daily",
    "bid": "twice daily",
    "tds": "three times daily",
    "tid": "three times daily",
    "qid": "four times daily",
    "qds": "four times daily",
    "hs": "at bedtime",
    "prn": "as needed",
    "sos": "if required",
    "stat": "immediately",
    "nocte": "at night",
    "mane": "in the morning",
}

_FREQ_PHRASES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), canonical)
    for pattern, canonical in (
        (r"\bonce\s+(?:a\s+)?daily\b", "once daily"),
        (r"\b(?:once|twice|thrice)?\s*(?:daily|every\s+day)\b", "once daily"),
        (r"\btwice\s+(?:a\s+)?(?:day|daily)\b", "twice daily"),
        (r"\b(?:two|2)\s+times?\s+(?:a\s+)?(?:day|daily)\b", "twice daily"),
        (r"\b(?:three|3|thrice)\s+times?\s+(?:a\s+)?(?:day|daily)\b", "three times daily"),
        (r"\b(?:four|4)\s+times?\s+(?:a\s+)?(?:day|daily)\b", "four times daily"),
        (r"\bevery\s+(\d{1,2})\s*(?:hours?|hrs?|h)\b", "every {} hours"),
        (r"\bat\s+bedtime\b", "at bedtime"),
        (r"\bbefore\s+(?:food|meals?|breakfast)\b", "before food"),
        (r"\bafter\s+(?:food|meals?|breakfast)\b", "after food"),
        (r"\bwith\s+food\b", "with food"),
        (r"\bempty\s+stomach\b", "empty stomach"),
        (r"\bas\s+(?:and\s+when\s+)?(?:needed|required)\b", "as needed"),
        (r"\b(?:1|2|3)\s*[-–]\s*(?:0|1|2|3)\s*[-–]\s*(?:0|1|2|3)\b", "dose pattern"),
    )
)

_FREQ_ABBR_RE = re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(_FREQ_ABBR) + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)

_DIAGNOSIS_LABEL_RE = re.compile(
    r"(?:provisional\s+diagnosis|final\s+diagnosis|diagnosis|d\s*[/.]\s*x|dx|"
    r"impression|complaints?|c\s*/\s*o)\s*[:\-]\s*(.+)",
    re.IGNORECASE,
)

#: Tokens that are formatting noise rather than drug names.
_STOPWORDS: frozenset[str] = frozenset(
    """
    the and for with from this that patient name age sex date address rx
    sig directions days day week weeks month months duration take taken
    morning night evening afternoon before after food meal meals empty stomach
    once twice thrice daily tablets tablet capsules as needed required if
    doctor dr hospital clinic prescription advise advised follow followup
    review test tests advice notes note signature signature reg regno
    """.split()
)


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

def find_drugs(text: str) -> list[str]:
    """Lexicon matches, deduplicated, in order of first appearance."""
    seen: dict[str, None] = {}
    for match in _DRUG_RE.finditer(text or ""):
        seen.setdefault(match.group(0).lower(), None)
    return list(seen)


def find_dosages(text: str) -> list[str]:
    """Dose strengths such as ``"650 mg"`` or bare ``"650"`` when unlabelled."""
    found: dict[str, None] = {}
    for match in _DOSAGE_RE.finditer(text or ""):
        value, unit = match.group(1), match.group(2).lower()
        found.setdefault(f"{value} {unit}", None)
    if not found:
        for match in _BARE_STRENGTH_RE.finditer(text or ""):
            found.setdefault(match.group(1), None)
    return list(found)


def find_frequencies(text: str) -> list[str]:
    """Canonical frequency strings, abbreviated forms expanded."""
    found: dict[str, None] = {}
    for pattern, canonical in _FREQ_PHRASES:
        for match in pattern.finditer(text or ""):
            value = canonical.format(*match.groups()) if "{}" in canonical else canonical
            if value != "dose pattern":
                found.setdefault(value, None)
    for match in _FREQ_ABBR_RE.finditer(text or ""):
        found.setdefault(_FREQ_ABBR[match.group(1).lower()], None)
    return list(found)


def find_diagnosis(text: str) -> str:
    """Labelled diagnosis line if present, else the first condition match."""
    labelled = None
    for match in _DIAGNOSIS_LABEL_RE.finditer(text or ""):
        candidate = normalize_whitespace(match.group(1))
        if candidate:
            labelled = candidate
            break
    if labelled:
        # Keep the line short: a diagnosis field should not swallow the page.
        return labelled[:160]
    condition = _CONDITION_RE.search(text or "")
    return normalize_whitespace(condition.group(0)).lower() if condition else ""


#: Strength/dose noise that is not part of a drug's *name*.
_DRUG_NAME_NOISE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*"
    r"(?:mg|mcg|µg|ug|g|gm|gram|grams|ml|cc|iu|units?|%|puffs?|drops?|tsp|tbsp)\b",
    re.IGNORECASE,
)


def normalize_drug_name(name: str) -> str:
    """Reduce a drug mention to a comparable name.

    ``"Tab. Dolo 650 mg"`` and ``"dolo"`` both become ``"dolo"``. Needed
    wherever two sources are compared, because one will list strengths and the
    other will not — and a difference in *dose* is not a disagreement about
    which drug was prescribed.
    """
    cleaned = _FORM_PREFIX_RE.sub("", name or "")
    cleaned = _DRUG_NAME_NOISE_RE.sub(" ", cleaned)
    cleaned = cleaned.replace("-", " ")
    cleaned = re.sub(r"[^A-Za-z0-9 ]", " ", cleaned)
    return normalize_whitespace(cleaned).lower()


_MONTH = r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"

_DATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\b"),
    re.compile(r"\b(\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2})\b"),
    re.compile(rf"\b(\d{{1,2}}\s+(?:{_MONTH})[a-z]*\.?\s+\d{{2,4}})\b", re.IGNORECASE),
    re.compile(rf"\b((?:{_MONTH})[a-z]*\.?\s+\d{{1,2}},?\s+\d{{2,4}})\b", re.IGNORECASE),
)


def find_date(text: str) -> str:
    """First date-looking substring, normalised. Empty string when absent.

    Prescription dates matter clinically (a course started last year is not the
    same as one started this week), so they are captured rather than dropped.
    """
    for pattern in _DATE_PATTERNS:
        match = pattern.search(text or "")
        if match:
            return normalize_whitespace(match.group(1))
    return ""


def candidate_drugs_from_lines(text: str) -> list[str]:
    """Recover drug names a lexicon cannot know.

    A dose-bearing line almost always leads with the drug, optionally behind a
    dosage form ("Tab. Azee 500"). When no lexicon entry matches, the leading
    token is taken instead so unseen brands still surface.
    """
    candidates: dict[str, None] = {}
    for raw_line in (text or "").splitlines():
        line = normalize_whitespace(raw_line)
        if not line or not (_DOSAGE_RE.search(line) or _FREQ_ABBR_RE.search(line)):
            continue
        stripped = _FORM_PREFIX_RE.sub("", line)
        for token in re.split(r"[\s,;/|]+", stripped):
            word = token.strip(".-:()")
            if len(word) < 4 or not word.isalpha():
                continue
            if word.lower() in _STOPWORDS:
                continue
            if word.lower() in DRUG_LEXICON:
                break  # lexicon already covers this line
            candidates.setdefault(word.lower(), None)
            break
    return list(candidates)


def extract_entities(text: str) -> dict[str, object]:
    """Full rule-based extraction, matching the ``/ner`` response contract."""
    text = text or ""
    drugs = find_drugs(text)
    for candidate in candidate_drugs_from_lines(text):
        if candidate not in drugs:
            drugs.append(candidate)
    return {
        "drugs": drugs,
        "dosages": find_dosages(text),
        "frequencies": find_frequencies(text),
        "diagnosis": find_diagnosis(text),
        "date": find_date(text),
        "lexicon_hits": sum(1 for drug in drugs if drug in DRUG_LEXICON),
        "token_count": len(text.split()),
    }
