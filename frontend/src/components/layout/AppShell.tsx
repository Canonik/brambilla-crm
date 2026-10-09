import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { motion } from "motion/react";
import { Building2, Kanban, LayoutDashboard, LifeBuoy, Menu, MessageSquareText, Moon, Search, Users, X } from "lucide-react";
import { useAssistant } from "@/assistant/AssistantContext";
import { AssistantDrawer } from "@/assistant/AssistantDrawer";
import { AssistantMark } from "@/assistant/AssistantMark";
import { useCurrentUser } from "@/app/currentUser";
import { USING_MOCKS } from "@/api/transport";
import { Avatar } from "@/components/ui/Avatar";
import { Kbd } from "@/components/ui/Button";
import { NativeSelect } from "@/components/ui/Input";
import { PageTransition, SPRING } from "@/components/motion/primitives";
import { cn } from "@/lib/cn";
import { CommandPalette, PaletteTrigger } from "./CommandPalette";

const NAV = [
  { to: "/", label: "Home", icon: LayoutDashboard, end: true },
  { to: "/companies", label: "Companies", icon: Building2 },
  { to: "/contacts", label: "Contacts", icon: Users },
  { to: "/deals", label: "Deals", icon: Kanban },
  { to: "/dormant", label: "Dormant customers", icon: Moon },
  { to: "/tickets", label: "Tickets", icon: LifeBuoy },
  { to: "/assistant", label: "Assistant", icon: MessageSquareText },
];

/** Routes that render the conversation inline, so the side panel stays shut there. */
export const INLINE_ASSISTANT_ROUTES = new Set(["/", "/assistant"]);

function Wordmark() {
  return (
    <div className="flex items-center gap-2.5 px-3">
      <span className="inline-flex size-7 items-center justify-center rounded-md bg-white font-wide text-[15px] font-bold text-[#111]">B</span>
      <div className="leading-tight">
        <div className="font-wide text-[14px] font-semibold tracking-tight text-white">Brambilla</div>
        <div className="text-[11px] text-white/50">Forniture CRM</div>
      </div>
    </div>
  );
}

function Nav({ layoutId }: { layoutId: string }) {
  return (
    <nav className="flex flex-1 flex-col gap-0.5 px-2" aria-label="Main">
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            cn(
              "relative flex h-8 items-center gap-2.5 rounded-md px-2 text-[13px] font-medium transition-colors",
              isActive ? "text-ink" : "text-white/70 hover:bg-white/10 hover:text-white",
            )
          }
        >
          {({ isActive }) => (
            <>
              {isActive ? <motion.span layoutId={layoutId} className="absolute inset-0 rounded-md bg-white" transition={SPRING} aria-hidden /> : null}
              <item.icon className="relative size-4 shrink-0" aria-hidden />
              <span className="relative truncate">{item.label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const location = useLocation();
  const assistant = useAssistant();
  const { user, users, setUser } = useCurrentUser();
  const inline = INLINE_ASSISTANT_ROUTES.has(location.pathname);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  // Cmd/Ctrl+K opens the palette; Cmd/Ctrl+J talks to the assistant.
  const toggleAssistant = assistant.toggle;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      const key = e.key.toLowerCase();
      if (key === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      } else if (key === "j") {
        e.preventDefault();
        const composer = document.querySelector<HTMLTextAreaElement>("textarea[data-composer]");
        if (INLINE_ASSISTANT_ROUTES.has(window.location.pathname) && composer) composer.focus();
        else toggleAssistant();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleAssistant]);

  const askButton = (
    <button
      type="button"
      onClick={() => {
        if (inline) document.querySelector<HTMLTextAreaElement>("textarea[data-composer]")?.focus();
        else assistant.toggle();
      }}
      className={cn(
        "group flex h-10 items-center gap-2.5 rounded-md px-2.5 text-left text-[13px] font-semibold transition-colors",
        assistant.open && !inline ? "bg-white/85 text-[#111]" : "bg-white text-[#111] hover:bg-white/90",
      )}
      aria-pressed={assistant.open && !inline}
    >
      <AssistantMark size={20} />
      <span className="truncate">Ask the CRM</span>
      <span className="ml-auto text-[11px] font-normal text-[#111]/50">⌘J</span>
    </button>
  );

  const footer = (
    <div className="mt-auto flex flex-col gap-2 border-t border-white/10 px-2 pt-3">
      {askButton}
      <label className="flex items-center gap-2 rounded-md px-1 py-1">
        <Avatar name={user.name} size="sm" />
        <span className="sr-only">Working as</span>
        <NativeSelect
          value={user.email}
          onChange={(e) => setUser(e.target.value)}
          options={users.map((u) => ({ value: u.email, label: u.name }))}
          className="min-w-0 flex-1 [&>select]:h-7 [&>select]:border-transparent [&>select]:bg-transparent [&>select]:px-1 [&>select]:text-[12.5px] [&>select]:text-white [&>select]:hover:border-white/30 [&>svg]:text-white/60"
          aria-label="Working as"
        />
      </label>
      {USING_MOCKS ? (
        <div className="mb-1 rounded-sm border border-dashed border-warn/50 bg-warn-soft px-2 py-1 text-center text-[11px] font-medium text-warn">
          Demo data · not connected to the API
        </div>
      ) : null}
    </div>
  );

  return (
    <div className="flex h-full min-h-0">
      <aside className="hidden w-56 shrink-0 flex-col gap-3 bg-[#111] py-3 md:flex">
        <Wordmark />
        <div className="px-2">
          <PaletteTrigger dark onOpen={() => setPaletteOpen(true)} />
        </div>
        <Nav layoutId="nav-active-desktop" />
        {footer}
      </aside>

      {/* Mobile top bar */}
      <div className="fixed inset-x-0 top-0 z-20 flex h-12 items-center justify-between border-b border-white/10 bg-[#111] px-2 md:hidden">
        <Wordmark />
        <div className="flex items-center gap-0.5">
          <button type="button" aria-label="Search or ask" onClick={() => setPaletteOpen(true)} className="rounded-md p-2 text-white/80 hover:bg-white/10">
            <Search className="size-5" />
          </button>
          <button type="button" aria-label="Ask the CRM" onClick={() => (inline ? document.querySelector<HTMLTextAreaElement>("textarea[data-composer]")?.focus() : assistant.toggle())} className="rounded-md p-2 hover:bg-white/10">
            <AssistantMark size={20} />
          </button>
          <button type="button" aria-label={mobileOpen ? "Close menu" : "Open menu"} aria-expanded={mobileOpen} onClick={() => setMobileOpen((o) => !o)} className="rounded-md p-2 text-white hover:bg-white/10">
            {mobileOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </div>
      {mobileOpen ? (
        <div className="fixed inset-0 top-12 z-20 flex flex-col gap-3 bg-[#111] py-3 md:hidden">
          <Nav layoutId="nav-active-mobile" />
          {footer}
        </div>
      ) : null}

      <main
        className={cn(
          "flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto scroll-quiet pt-12 transition-[margin] duration-200 md:pt-0",
          assistant.open && !inline && "xl:mr-[440px]",
        )}
      >
        <PageTransition>
          <Outlet />
        </PageTransition>
      </main>
      <AssistantDrawer />
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <span className="sr-only">Press {"⌘"}K to search, {"⌘"}J to ask the assistant. <Kbd>Esc</Kbd> closes.</span>
    </div>
  );
}
