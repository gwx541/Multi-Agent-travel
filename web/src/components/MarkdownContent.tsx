interface Props {
  html: string;
  className?: string;
}

export function MarkdownContent({ html, className }: Props) {
  return (
    <div
      className={className ? `markdown ${className}` : 'markdown'}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
