import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./endpoints";
import type { Deal, Pipeline, Props } from "./types";
import { pickSupportPipeline } from "@/lib/stages";

export const keys = {
  health: ["health"] as const,
  pipelines: (type: "deals" | "tickets") => ["pipelines", type] as const,
  companies: (params: api.CompanyListParams) => ["companies", params] as const,
  company: (id: string) => ["company", id] as const,
  contacts: (params: api.ContactListParams) => ["contacts", params] as const,
  contact: (id: string) => ["contact", id] as const,
  dealsInStage: (pipeline: string, stage: string) => ["deals", "stage", pipeline, stage] as const,
  deals: (params: api.DealListParams) => ["deals", "list", params] as const,
  deal: (id: string) => ["deal", id] as const,
  tickets: (params: api.TicketListParams) => ["tickets", params] as const,
  ticket: (id: string) => ["ticket", id] as const,
  dormant: ["dormant"] as const,
  activities: (key: string) => ["activities", key] as const,
  dashboard: ["dashboard"] as const,
};

export function useHealth() {
  return useQuery({ queryKey: keys.health, queryFn: api.getHealth, staleTime: 5 * 60_000, retry: 1 });
}

export function usePipelines(type: "deals" | "tickets") {
  return useQuery({ queryKey: keys.pipelines(type), queryFn: () => api.getPipelines(type), staleTime: 10 * 60_000 });
}

export function useCompanies(params: api.CompanyListParams) {
  return useInfiniteQuery({
    queryKey: keys.companies(params),
    queryFn: ({ pageParam }) => api.listCompanies({ ...params, after: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.paging?.next?.after,
  });
}

export function useCompanyPage(id: string | undefined) {
  return useQuery({ queryKey: keys.company(id ?? ""), queryFn: () => api.getCompanyPage(id!), enabled: Boolean(id) });
}

export function useContacts(params: api.ContactListParams) {
  return useInfiniteQuery({
    queryKey: keys.contacts(params),
    queryFn: ({ pageParam }) => api.listContacts({ ...params, after: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.paging?.next?.after,
  });
}

export function useContactPage(id: string | undefined) {
  return useQuery({ queryKey: keys.contact(id ?? ""), queryFn: () => api.getContactPage(id!), enabled: Boolean(id) });
}

export function useDealsInStage(pipeline: string | undefined, stage: string | undefined) {
  return useInfiniteQuery({
    queryKey: keys.dealsInStage(pipeline ?? "", stage ?? ""),
    queryFn: ({ pageParam }) => api.dealsInStage(pipeline!, stage!, { after: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.paging?.next?.after,
    enabled: Boolean(pipeline && stage),
  });
}

export function useDeals(params: api.DealListParams) {
  return useInfiniteQuery({
    queryKey: keys.deals(params),
    queryFn: ({ pageParam }) => api.listDeals({ ...params, after: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.paging?.next?.after,
  });
}

export function useDealPage(id: string | undefined) {
  return useQuery({ queryKey: keys.deal(id ?? ""), queryFn: () => api.getDealPage(id!), enabled: Boolean(id) });
}

export function useMoveDeal(pipeline: Pipeline | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ deal, toStage }: { deal: Deal; toStage: string }) => api.moveDeal(deal.id, toStage),
    onSuccess: async (_updated, { deal }) => {
      const pid = pipeline?.id ?? deal.properties.pipeline ?? "";
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["deals", "stage", pid] }),
        qc.invalidateQueries({ queryKey: keys.deal(deal.id) }),
        qc.invalidateQueries({ queryKey: keys.dashboard }),
      ]);
    },
  });
}

export function useTickets(params: api.TicketListParams) {
  return useInfiniteQuery({
    queryKey: keys.tickets(params),
    queryFn: ({ pageParam }) => api.listTickets({ ...params, after: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.paging?.next?.after,
  });
}

export function useTicketPage(id: string | undefined) {
  return useQuery({ queryKey: keys.ticket(id ?? ""), queryFn: () => api.getTicketPage(id!), enabled: Boolean(id) });
}

export function useUpdateTicket(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (props: Props) => api.updateTicket(id, props),
    onSuccess: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: keys.ticket(id) }),
        qc.invalidateQueries({ queryKey: ["tickets"] }),
        qc.invalidateQueries({ queryKey: keys.dashboard }),
      ]);
    },
  });
}

export function useDormantCompanies() {
  return useInfiniteQuery({
    queryKey: keys.dormant,
    queryFn: ({ pageParam }) => api.getDormantCompanies({ after: pageParam }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.paging?.next?.after,
    staleTime: 60_000,
  });
}

export function useActivities(
  key: string,
  targets: Array<{ type: "contacts" | "deals" | "companies" | "tickets"; ids: string[] }>,
  enabled = true,
) {
  return useQuery({
    queryKey: keys.activities(key),
    queryFn: () => api.activitiesFor(targets),
    enabled: enabled && targets.some((t) => t.ids.length > 0),
  });
}

export function useCreateNote(onDone?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { body: string; author: string | null; target: { type: "companies" | "contacts" | "deals" | "tickets"; id: string } }) =>
      api.createNote(vars.body, vars.author, vars.target),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["activities"] });
      onDone?.();
    },
  });
}

export function useDashboard(dealPipelines: Pipeline[] | undefined, ticketPipelines: Pipeline[] | undefined) {
  return useQuery({
    queryKey: [...keys.dashboard, dealPipelines?.map((p) => p.id).join(","), ticketPipelines?.map((p) => p.id).join(",")],
    enabled: Boolean(dealPipelines && ticketPipelines),
    queryFn: async () => {
      const sales = dealPipelines!.find((p) => p.id === "default") ?? dealPipelines![0];
      const support = pickSupportPipeline(ticketPipelines!);
      const stageCounts = sales
        ? await Promise.all(
            sales.stages.map(async (s) => ({
              stage: s,
              count: await api.countObjects("deals", [
                {
                  filters: [
                    { propertyName: "pipeline", operator: "EQ", value: sales.id },
                    { propertyName: "dealstage", operator: "EQ", value: s.id },
                  ],
                },
              ]),
            })),
          )
        : [];
      const ticketStageCounts = support
        ? await Promise.all(
            support.stages.map(async (s) => ({
              stage: s,
              count: await api.countObjects("tickets", [
                { filters: [{ propertyName: "hs_pipeline_stage", operator: "EQ", value: s.id }] },
              ]),
            })),
          )
        : [];
      const [companies, contacts, deals, tickets, recent, recentT, top] = await Promise.all([
        api.countObjects("companies"),
        api.countObjects("contacts"),
        api.countObjects("deals"),
        api.countObjects("tickets"),
        api.recentDeals(8),
        api.recentTickets(6),
        api.topCompanies(8),
      ]);
      return {
        sales,
        support,
        stageCounts,
        ticketStageCounts,
        totals: { companies, contacts, deals, tickets },
        recentDeals: recent.results ?? [],
        recentTickets: recentT.results ?? [],
        topCompanies: top.results ?? [],
      };
    },
    staleTime: 60_000,
  });
}
