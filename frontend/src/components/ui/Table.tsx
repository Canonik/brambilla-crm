import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { cn } from "@/lib/cn";

export function Table({ className, ...rest }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto scroll-quiet">
      <table className={cn("w-full border-collapse text-[13px]", className)} {...rest} />
    </div>
  );
}

export function THead({ className, ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("sticky top-0 z-[1] bg-surface-2", className)} {...rest} />;
}

export function TBody({ className, ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("[&>tr:last-child>td]:border-b-0", className)} {...rest} />;
}

export interface TRProps extends HTMLAttributes<HTMLTableRowElement> {
  interactive?: boolean;
}

export function TR({ className, interactive, ...rest }: TRProps) {
  return (
    <tr
      className={cn(
        "group",
        interactive && "cursor-pointer hover:bg-surface-2 focus-within:bg-surface-2 transition-colors duration-75",
        className,
      )}
      {...rest}
    />
  );
}

export interface THProps extends ThHTMLAttributes<HTMLTableCellElement> {
  align?: "left" | "right" | "center";
  sort?: "asc" | "desc" | null;
  onSort?: () => void;
}

export function TH({ className, align = "left", sort, onSort, children, ...rest }: THProps) {
  const content = (
    <span className={cn("inline-flex items-center gap-1", align === "right" && "flex-row-reverse")}>
      {children}
      {onSort ? (
        sort === "asc" ? (
          <ArrowUp className="size-3 text-ink-2" aria-hidden />
        ) : sort === "desc" ? (
          <ArrowDown className="size-3 text-ink-2" aria-hidden />
        ) : (
          <ArrowUpDown className="size-3 text-ink-3 opacity-0 group-hover/th:opacity-100" aria-hidden />
        )
      ) : null}
    </span>
  );
  return (
    <th
      scope="col"
      aria-sort={sort === "asc" ? "ascending" : sort === "desc" ? "descending" : undefined}
      className={cn(
        "group/th h-9 border-b border-line px-3 text-[12px] font-medium text-ink-2 whitespace-nowrap select-none",
        align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left",
        onSort && "cursor-pointer hover:text-ink",
        className,
      )}
      onClick={onSort}
      {...rest}
    >
      {content}
    </th>
  );
}

export interface TDProps extends TdHTMLAttributes<HTMLTableCellElement> {
  align?: "left" | "right" | "center";
  muted?: boolean;
  numeric?: boolean;
}

export function TD({ className, align = "left", muted, numeric, ...rest }: TDProps) {
  return (
    <td
      className={cn(
        "h-10 border-b border-line px-3 align-middle",
        align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left",
        muted && "text-ink-2",
        numeric && "tnum",
        className,
      )}
      {...rest}
    />
  );
}

export function TableFooter({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-center justify-between gap-3 border-t border-line px-3 py-2 text-[12px] text-ink-2", className)}>
      {children}
    </div>
  );
}
