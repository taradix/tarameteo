import { useTranslation } from 'react-i18next'
import './LanguageToggle.css'

function LanguageToggle() {
  const { i18n } = useTranslation()
  // resolvedLanguage maps a detected locale like "en-US" to a supported one ("en").
  const isEnglish = i18n.resolvedLanguage === 'en'

  const toggleLanguage = () => {
    i18n.changeLanguage(isEnglish ? 'fr' : 'en')
  }

  return (
    <button
      onClick={toggleLanguage}
      className="language-toggle"
      aria-label={isEnglish ? 'Passer en français' : 'Switch to English'}
    >
      {isEnglish ? 'FR' : 'EN'}
    </button>
  )
}

export default LanguageToggle
