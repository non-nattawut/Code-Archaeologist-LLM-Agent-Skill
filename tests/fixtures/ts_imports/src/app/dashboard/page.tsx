import Dashboard from "@/components/Dashboard";
import { handleSave, saveAction } from "@/lib/actions";

export default function DashboardPage() {
  return (
    <form action={saveAction}>
      <Dashboard />
      <button onClick={handleSave}>Save</button>
    </form>
  );
}
