import logging

from subburn.core.jobs import check_cancelled, update_job
from subburn.engines.base import TranslationEngine
from subburn.engines.registry import register_translation_engine

log = logging.getLogger("subburn")


# ---------------------------------------------------------------------------
# Translation (Argos Translate), with English-pivot fallback for language
# pairs that don't have a direct package - important for Persian, since Argos
# generally only ships direct packages to/from English.
# ---------------------------------------------------------------------------

def get_direct_translation(from_code: str, to_code: str):
    import argostranslate.package
    import argostranslate.translate

    def find(from_c, to_c):
        installed = argostranslate.translate.get_installed_languages()
        from_lang = next((l for l in installed if l.code == from_c), None)
        to_lang = next((l for l in installed if l.code == to_c), None)
        if from_lang and to_lang:
            return from_lang.get_translation(to_lang)
        return None

    translation = find(from_code, to_code)
    if translation:
        return translation

    argostranslate.package.update_package_index()
    available = argostranslate.package.get_available_packages()
    pkg = next((p for p in available if p.from_code == from_code and p.to_code == to_code), None)
    if pkg is None:
        return None
    path = pkg.download()
    argostranslate.package.install_from_path(path)
    return find(from_code, to_code)


def build_translate_fn(from_code: str, to_code: str):
    direct = get_direct_translation(from_code, to_code)
    if direct:
        return direct.translate

    if from_code != "en" and to_code != "en":
        to_en = get_direct_translation(from_code, "en")
        en_to_target = get_direct_translation("en", to_code)
        if to_en and en_to_target:
            log.info("No direct Argos package for '%s'->'%s'; pivoting through English", from_code, to_code)
            return lambda text: en_to_target.translate(to_en.translate(text))

    raise RuntimeError(
        f"No Argos Translate path found from '{from_code}' to '{to_code}' (direct or via English pivot)."
    )


def detect_segment_lang(text: str, primary_lang: str) -> str:
    # Podcasts that switch languages mid-recording (e.g. Arabic prayers/Quran
    # recitation inside a Persian podcast) get transcribed under one forced
    # language, but individual segments can still come out in whichever
    # language was actually spoken. Translating everything as if it were
    # primary_lang mistranslates (or garbles) those segments, so detect each
    # segment's actual text language and translate it with the right model.
    text = text.strip()
    if len(text) < 12:
        # Too short for language-id to be reliable; assume the file's
        # dominant language rather than risk a false-positive misroute.
        return primary_lang
    try:
        from langdetect import DetectorFactory, detect
        DetectorFactory.seed = 0
        return detect(text)
    except Exception:
        return primary_lang


class ArgosTranslationEngine(TranslationEngine):
    def translate_segments(self, job_id: str, segments: list[dict], from_code: str, to_code: str) -> list[dict]:
        translate_fns: dict[str, object] = {}

        def get_translate_fn(lang: str):
            if lang == to_code:
                # Already the target language - e.g. the file's dominant language
                # equals the requested subtitle language, so most segments need
                # no translation at all. Also avoids a same-language Argos
                # "translation" that would round-trip through English and
                # degrade otherwise-correct text.
                return lambda text: text
            if lang in translate_fns:
                return translate_fns[lang]
            try:
                fn = build_translate_fn(lang, to_code)
            except RuntimeError:
                log.warning("No Argos path for detected segment language '%s'->'%s'; using '%s' instead",
                            lang, to_code, from_code)
                fn = get_translate_fn(from_code)
            translate_fns[lang] = fn
            return fn

        primary_fn = get_translate_fn(from_code)
        failed_langs: set[str] = set()
        total = len(segments) or 1
        translated = []
        for i, seg in enumerate(segments):
            check_cancelled(job_id)
            text = seg["text"]
            seg_lang = detect_segment_lang(text, from_code)
            fn = primary_fn
            if seg_lang != from_code and seg_lang not in failed_langs:
                fn = get_translate_fn(seg_lang)
            try:
                out_text = fn(text)
            except Exception:
                # Some Argos language packages (e.g. langdetect false-positives
                # like 'tl' on garbled/short text) install fine but crash at
                # translate time - their sentence-splitter has no support for
                # that language. Don't let one bad segment kill the whole job:
                # fall back to the file's primary translator, and if even that
                # fails, keep the untranslated text.
                log.warning("Translation failed for detected language '%s' on segment %d; falling back",
                            seg_lang, i, exc_info=True)
                failed_langs.add(seg_lang)
                try:
                    out_text = primary_fn(text)
                except Exception:
                    out_text = text
            translated.append({**seg, "text": out_text})
            update_job(job_id, percent=60 + int((i + 1) / total * 15))
        return translated


register_translation_engine("argos", ArgosTranslationEngine())
