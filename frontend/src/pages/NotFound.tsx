import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/States";

export function NotFound() {
  return (
    <div className="flex flex-1 items-center justify-center">
      <EmptyState
        title="There is nothing at this address"
        description="The page may have moved, or the link was typed by hand."
        action={
          <Link to="/">
            <Button variant="secondary">Back to the dashboard</Button>
          </Link>
        }
      />
    </div>
  );
}
