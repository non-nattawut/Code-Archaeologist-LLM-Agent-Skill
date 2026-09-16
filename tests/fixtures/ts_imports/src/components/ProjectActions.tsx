import * as api from "@/services/api";
import { projectApi } from "@/lib/projectApi";
import { objectApi } from "@/lib/objectApi";

function useProjectApi() {
  return { listProjects: () => [] };
}

export function ProjectActions() {
  const hooked = useProjectApi();
  return (
    <div>
      <button onClick={() => api.approveSetdatProject("1")}>Approve</button>
      <button onClick={() => projectApi.approve("1")}>Approve again</button>
      <button onClick={() => objectApi.reject("1")}>Reject</button>
      <button onClick={() => objectApi.archive("1")}>Archive</button>
      <button onClick={() => hooked.listProjects()}>List</button>
    </div>
  );
}
