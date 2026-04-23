
from typing import Any, Dict

from core_llm.state_models import TripState
from tools.text_utils import merge_unique_csv

DEFAULT_BUDGET_LEVEL = "moderate"


def build_trip_planner_prompt(state: TripState) -> Dict[str, Any]:
    """Builds the prompt for the trip planner LLM."""

    req = state['trip_request']
    user_profile = state.get('user_profile', {})

    user_interests_str = merge_unique_csv(
        user_profile,
        'current_interests',
        'personal_interests'
    )

    user_language = user_profile.get('language', 'English')

    prompt = f"""
        # INPUT DATA
        - **Destination:** {req.get('destination')}
        - **Duration:** {req.get('duration')}
        - **Budget Level:** {req.get('budget', DEFAULT_BUDGET_LEVEL)}                        
        - **User Interests:** {user_interests_str}
        - **User Language:** {user_language}
                    
        - **Weather Information:** {state.get('weather')}                        
        
        - **BEGIN estimated Cost Data:** 
            {state.get('budget')}
        - **END estimated Cost Data**
        
        - ** BEGIN Local Research Data: ** 
            {state.get('research')}
        - ** END Local Research Data **

        # CONTENT GUIDELINES
        1. **Tone:** Professional, inspiring, and culturally respectful.
        2. **Integration:** You MUST weave the "Local Research Data" into the activities. Use specific names of landmarks, restaurants, or transport tips provided in the research.
        3. **Budget Adherence:** If the budget is "Budget," suggest street food and free walking tours. If "Luxury," suggest fine dining and private transfers.
        4. **Transport & Dining:** Every day MUST include at least one specific local dining suggestion and a "getting around" tip.

        # STRUCTURAL CONSTRAINTS (STRICT HTML)
        - **Introduction:** Start with a brief summary section in user language that includes:
            # Quick Summary
            <ul>
                <li><strong>Destination:</strong> ...</li>
                <li><strong>Trip Snapshot:</strong> Duration + Budget + Travel Style</li>
                <li><strong>Budget:</strong> ...</li>
                <li><strong>Interests:</strong> ...</li>
                <li><strong>Weather:</strong> ...</li>
                <li><strong>Top Experiences:</strong>
                    <ul>
                        <li>...</li>
                    </ul>
                </li>
                <li><strong>Where to Stay:</strong>
                    <ul>
                        <li>...</li>
                    </ul>
                </li>
            </ul>
        - **Daily Headers:** Daily Header begin with <h1>. Use exactly: <h1>Day N: [Catchy Theme Name]</h1>
        - **Timeline Sections:** Timeline Section use <h2>[Section Name]</h2>. Three section names: Morning, Afternoon, and Evening.
        - **Activities:** Use <ul> and <li> <strong> [Catchy Activity Name] </strong> for activities. Keep descriptions concise but vivid (2-3 sentences per activity).
        - **NO Meta-Talk:** Do not say "Here is your itinerary" or "I hope you enjoy it." Start directly with the summary.
        - **NO Questions:** Do not ask the user for feedback or more info.

        # OUTPUT 
        - The output MUST be in markdown format following the structure and tone guidelines above.
        - Generate the entire response ONLY in {user_language} language.            
    """

    return prompt
