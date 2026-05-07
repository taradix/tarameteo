import { useTranslation } from 'react-i18next'
import './LanguageToggle.css'

function LanguageToggle() {
  const { i18n } = useTranslation()

  const toggleLanguage = () => {
    const newLang = i18n.language === 'en' ? 'fr' : 'en'
    i18n.changeLanguage(newLang)
  }

  return (
    <button
      onClick={toggleLanguage}
      className="language-toggle"
      aria-label={i18n.language === 'en' ? 'Passer en français' : 'Switch to English'}
    >
      {i18n.language === 'en' ? 'FR' : 'EN'}
    </button>
  )
}

export default LanguageToggle
