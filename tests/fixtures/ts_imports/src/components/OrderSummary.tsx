import { formatSize } from "@/utils/fileSizeFormat";
import * as errors from "@/lib/apiError";
import { ApiError } from "@/lib/apiError";
import { label } from "@/lib/labels";

export function OrderSummary() {
  if (!formatSize) {
    throw new ApiError("no formatter");
  }
  return <p>{formatSize(1)} {errors.toMessage("x")} {label("y")}</p>;
}
