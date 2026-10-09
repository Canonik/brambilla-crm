import { useEffect } from "react";
import { useAssistant } from "@/assistant/AssistantContext";
import { AssistantChat } from "@/assistant/AssistantChat";
import { PageHeader } from "@/components/layout/PageHeader";
import { useCurrentUser } from "@/app/currentUser";

export function AssistantPage() {
  const { setOpen } = useAssistant();
  const { user } = useCurrentUser();
  useEffect(() => setOpen(false), [setOpen]);
  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <PageHeader
        title="Assistant"
        meta={
          <span>
            Writing as <span className="text-ink">{user.name}</span> · the assistant reads and updates the CRM with the same rules as every other screen
          </span>
        }
      />
      <div className="min-h-0 flex-1">
        <AssistantChat variant="page" />
      </div>
    </div>
  );
}
