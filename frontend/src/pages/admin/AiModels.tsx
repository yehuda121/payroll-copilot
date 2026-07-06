import { PortalPage } from '../../components/PortalPage';

export function AiModelsPage() {
  return (
    <PortalPage
      title="AI Models"
      description="Configure model provider, per-agent model selection, and Ollama/OpenAI settings. AI assists — never decides legality."
      integrationNote="@integration-point AI_MODELS — backend/config/ai_models.yaml"
    />
  );
}
