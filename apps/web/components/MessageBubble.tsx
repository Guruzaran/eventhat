"use client";

interface Props {
  role: "user" | "assistant";
  content: string;
}

function renderMarkdown(text: string) {
  // Basic markdown: **bold**, `code`, line breaks
  const lines = text.split("\n");
  return lines.map((line, i) => {
    const parts = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
    return (
      <span key={i}>
        {parts.map((part, j) => {
          if (part.startsWith("**") && part.endsWith("**")) {
            return <strong key={j}>{part.slice(2, -2)}</strong>;
          }
          if (part.startsWith("`") && part.endsWith("`")) {
            return (
              <code key={j} className="bg-black/20 px-1 rounded text-xs font-mono">
                {part.slice(1, -1)}
              </code>
            );
          }
          return part;
        })}
        {i < lines.length - 1 && <br />}
      </span>
    );
  });
}


export default function MessageBubble({ role, content }: Props) {
  const isUser = role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      {/* Avatar */}
      <div className={`w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold ${
        isUser ? "bg-[#1A56DB] text-white" : "bg-[#0D9488] text-white"
      }`}>
        {isUser ? "U" : "⚡"}
      </div>

      <div className={`flex flex-col gap-1 max-w-[75%] ${isUser ? "items-end" : "items-start"}`}>
        <div className={`px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
          isUser
            ? "bg-[#1A56DB] text-white rounded-tr-sm"
            : "bg-white text-gray-800 rounded-tl-sm shadow-sm"
        }`}>
          {renderMarkdown(content)}
        </div>
      </div>
    </div>
  );
}
