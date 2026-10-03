from pharmasense.orchestration.state import WorkflowState

class FinalizerNode:
    def __call__(self, state: WorkflowState) -> dict:
        # Formats the final output. The actual transformation to API response
        # can happen in the API layer, but this node ensures a clean final state.
        return state
