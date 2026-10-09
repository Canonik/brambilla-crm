import { Button } from "./Button";
import { TableFooter } from "./Table";
import { formatNumber } from "@/lib/format";

export function LoadMoreFooter({
  shown,
  total,
  hasMore,
  loading,
  onMore,
  noun = "records",
}: {
  shown: number;
  total: number | undefined;
  hasMore: boolean;
  loading: boolean;
  onMore: () => void;
  noun?: string;
}) {
  return (
    <TableFooter>
      <span className="tnum">
        Showing {formatNumber(shown)}
        {total !== undefined ? ` of ${formatNumber(total)}` : ""} {noun}
      </span>
      {hasMore ? (
        <Button size="sm" variant="secondary" loading={loading} onClick={onMore}>
          Load more
        </Button>
      ) : null}
    </TableFooter>
  );
}
