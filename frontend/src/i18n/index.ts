import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import zhCN from './locales/zh-CN.json';
import enUS from './locales/en-US.json';

/**
 * i18n 初始化
 * @see docs/design/20-i18n-localization.md
 */
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: 'zh-CN',
    debug: import.meta.env.DEV,
    resources: {
      'zh-CN': { translation: zhCN },
      'en-US': { translation: enUS },
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'hscredit-language',
    },
    interpolation: {
      escapeValue: false,
    },
  });

export default i18n;
