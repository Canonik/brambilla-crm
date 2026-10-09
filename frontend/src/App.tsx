import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ApiError } from "@/api/client";
import { AppShell } from "@/components/layout/AppShell";
import { ToastProvider } from "@/components/ui/Toaster";
import { TooltipProvider } from "@/components/ui/Tooltip";
import { CurrentUserProvider } from "@/app/currentUser";
import { AssistantProvider } from "@/assistant/AssistantContext";
import { TokenGate } from "@/auth/TokenGate";
import { MotionProvider } from "@/components/motion/primitives";
import { Home } from "@/pages/Home";
import { CompaniesList } from "@/pages/companies/CompaniesList";
import { CompanyDetail } from "@/pages/companies/CompanyDetail";
import { ContactsList } from "@/pages/contacts/ContactsList";
import { ContactDetail } from "@/pages/contacts/ContactDetail";
import { DealsBoard } from "@/pages/deals/DealsBoard";
import { DealDetail } from "@/pages/deals/DealDetail";
import { DormantCustomers } from "@/pages/dormant/DormantCustomers";
import { TicketsList } from "@/pages/tickets/TicketsList";
import { TicketDetail } from "@/pages/tickets/TicketDetail";
import { AssistantPage } from "@/pages/AssistantPage";
import { NotFound } from "@/pages/NotFound";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (count, error) => {
        if (error instanceof ApiError && (error.status === 401 || error.status === 404 || error.status === 400)) return false;
        return count < 2;
      },
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <TooltipProvider>
          <CurrentUserProvider>
            <TokenGate>
              <BrowserRouter>
                <MotionProvider>
                <AssistantProvider>
                  <Routes>
                    <Route element={<AppShell />}>
                      <Route index element={<Home />} />
                      <Route path="companies" element={<CompaniesList />} />
                      <Route path="companies/:id" element={<CompanyDetail />} />
                      <Route path="contacts" element={<ContactsList />} />
                      <Route path="contacts/:id" element={<ContactDetail />} />
                      <Route path="deals" element={<DealsBoard />} />
                      <Route path="deals/:id" element={<DealDetail />} />
                      <Route path="dormant" element={<DormantCustomers />} />
                      <Route path="dormant-customers" element={<Navigate to="/dormant" replace />} />
                      <Route path="tickets" element={<TicketsList />} />
                      <Route path="tickets/:id" element={<TicketDetail />} />
                      <Route path="assistant" element={<AssistantPage />} />
                      <Route path="*" element={<NotFound />} />
                    </Route>
                  </Routes>
                </AssistantProvider>
                </MotionProvider>
              </BrowserRouter>
            </TokenGate>
          </CurrentUserProvider>
        </TooltipProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
