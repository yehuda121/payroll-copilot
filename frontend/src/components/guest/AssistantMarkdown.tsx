import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import type { Components } from 'react-markdown';

type AssistantMarkdownProps = {
  content: string;
  className?: string;
};

/** Allow safe formatting tags only — no scripts, iframes, or event handlers. */
const sanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    a: [...(defaultSchema.attributes?.a ?? []), 'target', 'rel'],
    code: [...(defaultSchema.attributes?.code ?? []), 'className'],
  },
};

const components: Components = {
  a: ({ href, children, ...props }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
      {children}
    </a>
  ),
  pre: ({ children, ...props }) => (
    <pre dir="ltr" {...props}>
      {children}
    </pre>
  ),
  code: ({ className, children, ...props }) => {
    const isBlock = Boolean(className?.includes('language-'));
    if (isBlock) {
      return (
        <code className={className} dir="ltr" {...props}>
          {children}
        </code>
      );
    }
    return (
      <code className={className} dir="ltr" {...props}>
        {children}
      </code>
    );
  },
};

/**
 * Safe Markdown renderer for assistant chat answers.
 * Does not alter the AI response text — presentation only.
 */
export function AssistantMarkdown({ content, className }: AssistantMarkdownProps) {
  return (
    <div className={className ? `assistant-markdown ${className}` : 'assistant-markdown'}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSanitize, sanitizeSchema]]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
