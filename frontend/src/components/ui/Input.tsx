import { forwardRef, type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { ChevronDown, Search, X } from "lucide-react";
import { cn } from "@/lib/cn";

const field =
  "h-8 w-full rounded-md border border-line-strong bg-surface px-2.5 text-[13px] text-ink placeholder:text-ink-3 " +
  "transition-colors hover:border-ink-3 focus:border-gentian focus:outline-none focus:ring-2 focus:ring-gentian/20 " +
  "disabled:opacity-50";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...rest },
  ref,
) {
  return <input ref={ref} className={cn(field, className)} {...rest} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(
  { className, ...rest },
  ref,
) {
  return <textarea ref={ref} className={cn(field, "h-auto min-h-20 resize-y py-2 leading-normal", className)} {...rest} />;
});

export interface SearchInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> {
  value: string;
  onChange: (value: string) => void;
}

export function SearchInput({ value, onChange, className, placeholder = "Search", ...rest }: SearchInputProps) {
  return (
    <div className={cn("relative", className)}>
      <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-3" aria-hidden />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cn(field, "pl-8 pr-7 [&::-webkit-search-cancel-button]:hidden")}
        {...rest}
      />
      {value ? (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => onChange("")}
          className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded-sm p-0.5 text-ink-3 hover:bg-surface-3 hover:text-ink"
        >
          <X className="size-3.5" />
        </button>
      ) : null}
    </div>
  );
}

export interface NativeSelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  options: Array<{ value: string; label: string }>;
  placeholder?: string;
}

export const NativeSelect = forwardRef<HTMLSelectElement, NativeSelectProps>(function NativeSelect(
  { className, options, placeholder, ...rest },
  ref,
) {
  return (
    <div className={cn("relative", className)}>
      <select ref={ref} className={cn(field, "appearance-none pr-7", rest.value === "" && "text-ink-2")} {...rest}>
        {placeholder !== undefined ? <option value="">{placeholder}</option> : null}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute top-1/2 right-2 size-3.5 -translate-y-1/2 text-ink-3" aria-hidden />
    </div>
  );
});

export function Label({ children, htmlFor, className }: { children: React.ReactNode; htmlFor?: string; className?: string }) {
  return (
    <label htmlFor={htmlFor} className={cn("block text-[12px] font-medium text-ink-2", className)}>
      {children}
    </label>
  );
}
