import type { DdlPlan, DdlReminder, SmartCoreEvent } from "@/types/event";

export function cloneDdlRelations(event: SmartCoreEvent): {
  plans: DdlPlan[];
  ddlReminders: DdlReminder[];
} {
  if (event.evtType !== "ddl") return { plans: [], ddlReminders: [] };
  return {
    plans: (event.plans ?? []).map((plan) => ({ ...plan })),
    ddlReminders: (event.ddlReminders ?? []).map((reminder) => ({ ...reminder })),
  };
}
