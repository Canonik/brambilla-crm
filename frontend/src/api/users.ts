import type { CrmUser } from "./types";

// Brambilla's active users, as listed in the legacy export's utenti.csv. The
// assistant contract needs `context.user` to be one of them, and the UI uses
// the list to show who follows a deal or ticket by name.
export const USERS: CrmUser[] = [
  { email: "nicolo.deluca@brambillaforniture.it", name: "Nicolò De Luca", role: "Sales director" },
  { email: "silvia.basile@brambillaforniture.it", name: "Silvia Basile", role: "Area manager" },
  { email: "ilaria.borghi@brambillaforniture.it", name: "Ilaria Borghi", role: "Area manager" },
  { email: "chiara.tagliabue@brambillaforniture.it", name: "Chiara Tagliabue", role: "Area manager" },
  { email: "giuseppe.panzeri@brambillaforniture.it", name: "Giuseppe Panzeri", role: "Area manager" },
  { email: "cristina.mapelli@brambillaforniture.it", name: "Cristina Mapelli", role: "Area manager" },
  { email: "monica.guerra@brambillaforniture.it", name: "Monica Guerra", role: "Area manager" },
  { email: "irene.pellegrini@brambillaforniture.it", name: "Irene Pellegrini", role: "Area manager" },
  { email: "riccardo.mancini@brambillaforniture.it", name: "Riccardo Mancini", role: "Sales rep" },
  { email: "francesca.redaelli@brambillaforniture.it", name: "Francesca Redaelli", role: "Sales rep" },
  { email: "marco.rossi@brambillaforniture.it", name: "Marco Rossi", role: "Sales rep" },
  { email: "roberta.redaelli@brambillaforniture.it", name: "Roberta Redaelli", role: "Sales rep" },
  { email: "noemi.dalo@brambillaforniture.it", name: "Noemi Dalò", role: "Sales rep" },
  { email: "luca.ferrari@brambillaforniture.it", name: "Luca Ferrari", role: "Sales rep" },
  { email: "tommaso.lombardo@brambillaforniture.it", name: "Tommaso Lombardo", role: "Sales rep" },
  { email: "davide.mauri@brambillaforniture.it", name: "Davide Mauri", role: "Sales rep" },
  { email: "andrea.pozzi@brambillaforniture.it", name: "Andrea Pozzi", role: "Sales rep" },
  { email: "franco.valsecchi@brambillaforniture.it", name: "Franco Valsecchi", role: "Sales rep" },
  { email: "debora.pozzi@brambillaforniture.it", name: "Débora Pozzi", role: "Sales rep" },
  { email: "daniele.palumbo@brambillaforniture.it", name: "Daniele Palumbo", role: "Sales rep" },
  { email: "stefano.marchetti@brambillaforniture.it", name: "Stefano Marchetti", role: "Sales rep" },
  { email: "giorgia.rota@brambillaforniture.it", name: "Giorgia Rota", role: "Sales rep" },
  { email: "noemi.pellegrini@brambillaforniture.it", name: "Noemi Pellegrini", role: "Sales rep" },
  { email: "silvia.dellacqua@brambillaforniture.it", name: "Silvia Dell'Acqua", role: "Sales rep" },
  { email: "niccolo.mauri@brambillaforniture.it", name: "Niccolò Mauri", role: "Sales rep" },
  { email: "francesca.marchetti@brambillaforniture.it", name: "Francesca Marchetti", role: "Sales rep" },
  { email: "elisa.mazza@brambillaforniture.it", name: "Elisa Mazza", role: "Sales rep" },
  { email: "enrico.rinaldi@brambillaforniture.it", name: "Enrico Rinaldi", role: "Sales rep" },
  { email: "andrea.rota@brambillaforniture.it", name: "Andrea Rota", role: "Sales rep" },
  { email: "elena.silvestri@brambillaforniture.it", name: "Elena Silvestri", role: "Sales rep" },
  { email: "mattia.vigano@brambillaforniture.it", name: "Mattia Viganò", role: "Sales rep" },
  { email: "anna.sala@brambillaforniture.it", name: "Anna Sala", role: "Sales rep" },
];

// The fallback above is only used until the API's owners have loaded; the
// migrated export decides who the real users are.
const byEmail = new Map(USERS.map((u) => [u.email.toLowerCase(), u]));
let known: Map<string, CrmUser> = byEmail;

export function setKnownUsers(users: CrmUser[]) {
  known = new Map(users.map((u) => [u.email.toLowerCase(), u]));
}

export function userByEmail(email: string | null | undefined): CrmUser | null {
  if (!email) return null;
  const key = email.trim().toLowerCase();
  return known.get(key) ?? byEmail.get(key) ?? null;
}

export function userName(email: string | null | undefined, fallback = "Unassigned"): string {
  if (!email) return fallback;
  const u = userByEmail(email);
  if (u) return u.name;
  const local = email.split("@")[0] ?? email;
  return local
    .split(/[._-]+/)
    .filter(Boolean)
    .map((p) => p[0]!.toUpperCase() + p.slice(1))
    .join(" ");
}

export const DEFAULT_USER = USERS[USERS.length - 1]!;
