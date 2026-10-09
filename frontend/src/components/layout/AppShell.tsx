import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Building2, Kanban, LayoutDashboard, LifeBuoy, Menu, MessageSquareText, Moon, Users, X } from "lucide-react";
import { useAssistant } from "@/assistant/AssistantContext";
import { AssistantDrawer } from "@/assistant/AssistantDrawer";
import { AssistantMark } from "@/assistant/AssistantChat";
import { useCurrentUser } from "@/app/currentUser";
import { USING_MOCKS } from "@/api/transport";
import { Avatar } from "@/components/ui/Avatar";
import { NativeSelect } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import { GlobalSearch } from "./GlobalSearch";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/companies", label: "Companies", icon: Building2 },
  { to: "/contacts", label: "Contacts", icon: Users },
  { to: "/deals", label: "Deals", icon: Kanban },
  { to: "/dormant", label: "Dormant customers", icon: Moon },
  { to: "/tickets", label: "Tickets", icon: LifeBuoy },
  { to: "/assistant", label: "Assistant", icon: MessageSquareText },
];

function Wordmark() {
  return (
    <div className="flex items-center gap-2.5 px-3">
      <span className="inline-flex size-7 items-center justify-center rounded-md bg-gentian font-wide text-[15px] font-bold text-white">
        B
      </span>
      <div className="leading-tight">
        <div className="font-wide text-[14px] font-semibold tracking-tight text-ink">Brambilla</div>
        <div className="text-[11px] text-ink-3">Forniture CRM</div>
      </div>
    </div>
  );
}

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const assistant = useAssistant();
  const { user, users, setUser } = useCurrentUser();

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const nav = (
    <nav className="flex flex-1 flex-col gap-0.5 px-2" aria-label="Main">
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            cn(
              "flex h-8 items-center gap-2.5 rounded-md px-2 text-[13px] font-medium transition-colors",
              isActive ? "bg-gentian-soft text-gentian" : "text-ink-2 hover:bg-surface-3 hover:text-ink",
            )
          }
        >
          <item.icon className="size-4 shrink-0" aria-hidden />
          <span className="truncate">{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );

  const footer = (
    <div className="mt-auto flex flex-col gap-2 border-t border-line px-2 pt-3">
      <button
        type="button"
        onClick={assistant.toggle}
        className={cn(
          "flex h-9 items-center gap-2.5 rounded-md border px-2 text-left text-[13px] font-medium transition-colors",
          assistant.open ? "border-gentian-line bg-gentian-soft text-gentian" : "border-line bg-surface text-ink hover:border-gentian-line hover:bg-gentian-soft/50",
        )}
        aria-pressed={assistant.open}
      >
        <AssistantMark size={18} />
        <span className="truncate">Ask the CRM</span>
        <span className="ml-auto text-[11px] font-normal text-ink-3">Esc</span>
      </button>
      <label className="flex items-center gap-2 rounded-md px-1 py-1">
        <Avatar name={user.name} size="sm" />
        <span className="sr-only">Working as</span>
        <NativeSelect
          value={user.email}
          onChange={(e) => setUser(e.target.value)}
          options={users.map((u) => ({ value: u.email, label: u.name }))}
          className="min-w-0 flex-1 [&>select]:h-7 [&>select]:border-transparent [&>select]:bg-transparent [&>select]:px-1 [&>select]:text-[12.5px] [&>select]:hover:border-line-strong"
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
      <aside className="hidden w-60 shrink-0 flex-col gap-3 border-r border-line bg-surface py-3 md:flex">
        <Wordmark />
        <GlobalSearch />
        {nav}
        {footer}
      </aside>

      {/* Mobile top bar */}
      <div className="fixed inset-x-0 top-0 z-20 flex h-12 items-center justify-between border-b border-line bg-surface px-2 md:hidden">
        <Wordmark />
        <div className="flex items-center gap-1">
          <button type="button" aria-label="Ask the CRM" onClick={assistant.toggle} className="rounded-md p-2 hover:bg-surface-3">
            <AssistantMark size={18} />
          </button>
          <button type="button" aria-label={mobileOpen ? "Close menu" : "Open menu"} onClick={() => setMobileOpen((o) => !o)} className="rounded-md p-2 hover:bg-surface-3">
            {mobileOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </div>
      {mobileOpen ? (
        <div className="fixed inset-0 top-12 z-20 flex flex-col gap-3 bg-surface py-3 md:hidden">
          <GlobalSearch onNavigate={() => setMobileOpen(false)} />
          {nav}
          {footer}
        </div>
      ) : null}

      <main
        className={cn(
          "flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto scroll-quiet pt-12 transition-[margin] duration-200 md:pt-0",
          assistant.open && "xl:mr-[440px]",
        )}
      >
        <Outlet />
      </main>
      <AssistantDrawer />
    </div>
  );
}
