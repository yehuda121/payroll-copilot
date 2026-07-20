import { Component, type ErrorInfo, type ReactNode } from 'react';
import { withTranslation, type WithTranslation } from 'react-i18next';

type Props = WithTranslation & {
  children: ReactNode;
  /** Optional label for logs (e.g. portal name). */
  scope?: string;
};

type State = {
  hasError: boolean;
};

/**
 * Production-grade boundary: isolates a subtree failure so the rest of the app
 * (navigation, sibling portals) can keep working. UX stays minimal and on-brand.
 */
class ErrorBoundaryBase extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    const scope = this.props.scope ? ` [${this.props.scope}]` : '';
    console.error(`UI ErrorBoundary${scope}`, error, info.componentStack);
  }

  private handleRetry = (): void => {
    this.setState({ hasError: false });
  };

  render(): ReactNode {
    const { t, children } = this.props;
    if (this.state.hasError) {
      return (
        <div className="app-error-boundary" role="alert">
          <h1 className="app-error-boundary__title">{t('common.error')}</h1>
          <p className="app-error-boundary__message">{t('common.errorBoundaryMessage')}</p>
          <button type="button" className="btn btn--secondary" onClick={this.handleRetry}>
            {t('common.retry')}
          </button>
        </div>
      );
    }
    return children;
  }
}

export const ErrorBoundary = withTranslation()(ErrorBoundaryBase);
