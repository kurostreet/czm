/* Translations are local presentation, never substituted into messages or reports. */
#pragma once
struct CzmTranslationView {
    int state; // 0 idle, 1 pending, 2 ready, 3 retry
    bool shown;
    const char *text;
};
bool CZM_TranslationAvailable();
int CZM_TranslationStart(const char *text,bool russian);
bool CZM_CanTranslate(const char *text);
CzmTranslationView CZM_TranslationGet(const char *text);
void CZM_Translate(const char *text);
void CZM_TranslationFrame();
