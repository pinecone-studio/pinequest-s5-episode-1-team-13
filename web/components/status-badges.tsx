import { Badge } from "@/components/ui/badge";
import { CAMERA_STATUS_LABEL, cameraTone, STATUS_LABEL, TONE_CLASS, VIOLATION_LABEL, VIOLATION_STATUS_CLASS } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CameraStatus, ViolationStatus, ViolationType } from "@/types";

export function CameraStatusBadge({ status, className }: { status: CameraStatus; className?: string }) {
  return (
    <Badge variant="outline" className={cn("gap-1.5", TONE_CLASS[cameraTone(status)], className)}>
      <span className="size-1.5 rounded-full bg-current" />
      {CAMERA_STATUS_LABEL[status]}
    </Badge>
  );
}

export function ViolationStatusBadge({ status, className }: { status: ViolationStatus; className?: string }) {
  return (
    <Badge variant="outline" className={cn(VIOLATION_STATUS_CLASS[status], className)}>
      {STATUS_LABEL[status]}
    </Badge>
  );
}

export function ViolationTypeBadge({ type, className }: { type: ViolationType; className?: string }) {
  return (
    <Badge variant="outline" className={cn("border-danger/30 bg-danger/10 text-danger", className)}>
      {VIOLATION_LABEL[type]}
    </Badge>
  );
}
