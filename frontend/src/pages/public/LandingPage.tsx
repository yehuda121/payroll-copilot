import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { HeroSplit } from '../../components/layout/HeroSplit';
import { PageContainer } from '../../components/layout/PageContainer';
import { APP_NAME } from '../../config/brand';
import { GuestLandingChat } from '../../features/guest/landing/GuestLandingChat';
import '../../features/guest/guest.css';

/**
 * Public landing — marketing hero + existing guest chat (unchanged capabilities).
 */
export function LandingPage() {
  const { t } = useTranslation();
  const [popularQuestionsHost, setPopularQuestionsHost] = useState<HTMLDivElement | null>(null);

  return (
    <div className="landing-page">
      <PageContainer width="wide">
        <HeroSplit
          copy={
            <>
              <p className="hero-brand">{APP_NAME}</p>
              <h1 className="hero-title">{t('landing.heroHeadline')}</h1>
              <p className="hero-subtitle">{t('landing.heroSubtitle')}</p>
              <p className="hero-disclaimer">{t('landing.heroDisclaimer')}</p>
              <div ref={setPopularQuestionsHost} />
            </>
          }
          media={
            <div className="landing-page__chat-column">
              <GuestLandingChat showWelcome popularQuestionsHost={popularQuestionsHost} />
            </div>
          }
        />
      </PageContainer>
    </div>
  );
}
