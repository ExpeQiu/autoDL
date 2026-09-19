import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", id: "studio", label: "测试页面" },
  { href: "/services", id: "services", label: "服务配置" },
] as const;

export function SiteNav({ current }: { current: (typeof LINKS)[number]["id"] }) {
  return (
    <nav className="flex gap-1 rounded-md bg-stone-900 p-1 text-sm">
      {LINKS.map((link) => (
        <a
          key={link.id}
          href={link.href}
          className={cn(
            "rounded px-3 py-1.5",
            current === link.id ? "bg-stone-700 text-white" : "text-stone-400 hover:text-stone-200",
          )}
        >
          {link.label}
        </a>
      ))}
    </nav>
  );
}
