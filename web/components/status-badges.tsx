import { Badge } from "@/components/ui/badge";
import { CAMERA_STATUS_LABEL, cameraTone, STATUS_LABEL, TONE_CLASS, VIOLATION_LABEL, VIOLATION_STATUS_CLASS } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CameraStatus, ViolationStatus, ViolationType } from "@/types";

export function CameraStatusBadge({ status }: { status: CameraStatus }) {
  return (
    <Badge variant="outline" className={cn("gap-1.5", TONE_CLASS[cameraTone(status)])}>
      <span className="size-1.5 rounded-full bg-current" />
      {CAMERA_STATUS_LABEL[status]}
    </Badge>
  );
}

export function ViolationStatusBadge({ status }: { status: ViolationStatus }) {
  return (
    <Badge variant="outline" className={VIOLATION_STATUS_CLASS[status]}>
      {STATUS_LABEL[status]}
    </Badge>
  );
}

export function ViolationTypeBadge({ type }: { type: ViolationType }) {
  return (
    <Badge variant="outline" className="border-red-500/30 bg-red-500/10 text-red-300">
      {VIOLATION_LABEL[type]}
    </Badge>
  );
}
