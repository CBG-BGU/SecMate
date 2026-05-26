# Dataset Description and Column Definitions

The dataset file, `secmate_data.csv`, contains the results of a controlled human-subjects experiment evaluating SecMate, a personalized, agentic chatbot for cybersecurity troubleshooting. The following sections describe the dataset structure and explain the meaning of each column.

## Participant and Conversation Identifiers
-   `email_id`: An anonymized unique identifier for each participant in the experiment.
-   `scenario`: An integer from 1 to 5, indicating the scenario number for that participant's session. This column indicates the order of conversations for that participant.
-   `scenario_title`: The title of the troubleshooting scenario for the conversation (e.g., "PC Performance," "Airport Wi-Fi").
-   `conversation`: The full transcript of the conversation between the participant and the chatbot.

The combination of `email_id` and `scenario` uniquely identifies each row.

## Experimental Variables & Configuration
-   `config`: The SecMate configuration used for the conversation, as part of an ablation study testing different capabilities. The possible values are:
    -   `'SecMate_Both'`: SecMate with both ClueCollector (device specificity) and Adaptation (user specificity) enabled.
    -   `'SecMate_CC'`: SecMate with only the ClueCollector enabled.
    -   `'SecMate_Adap'`: SecMate with only Adaptation enabled.
    -   `'SecMate_None'`: SecMate with neither ClueCollector nor Adaptation enabled.
    -   `'Chabot_Baseline'`: A baseline configuration using ChatGPT with a simple system prompt, without SecMate's agentic logic.
-   `CC`: Defines the refresh rate of the **ClueCollector** (CC), a local diagnostic utility that gathers system information.
    -   `'Once'`: Gathers information once at the start.
    -   `'Multi'`: Refreshes every 60 seconds.
    -   `'Multi-5'`: Refreshes every 5 seconds.
-   `PI`: The method used for **Adaptation**, which tailors guidance to the user's technical knowledge.
    -   `'Real'`: Uses the user's actual self-reported tech knowledge.
    -   `'All-5'`: Assumes the user is an expert (all proficiency ratings set to 5).
    -   `'All-1'`: Assumes the user is a novice (all proficiency ratings set to 1).
-   `RF`: The format used to present product recommendations.
    -   `'IC'`: In-Conversation.
    -   `'PU'`: Pop-Up.
    -   `'PUM'`: Pop-Up with a minimize option.

## Pre-Experiment Questionnaire (Participant Information)
Before the experiment, participants provided the following demographic and background information. These fields were optional and may contain null values.

-   `age`: Participant's age.
-   `gender`: Participant's gender.
-   `status`: Participant's current status (e.g., "B.Sc tudent").
-   `stem_background`: Indicates if the participant has a background in STEM (Science, Technology, Engineering, or Mathematics).
-   `years_of_education`: Participant's total years of education.
-   `english_level`: Participant's self-reported English proficiency level (1-5).

## Tech 5 User Profile
These columns capture the participant’s self-reported technical proficiency across five domains and their subdomains.  
Each column is named in the format `Domain.Subdomain`, for example:
-   `Networking.General`  
-   `Networking.Configuration`  
-   `Security.Data Leakage`  
-   `Operating_Systems.File Management`  
-   `Hardware.Ram and Memory`

## Post-Scenario Questionnaire (Conversation-Level Feedback)
After each of the five conversations, participants completed a survey.
-   `pleasant_experience`: Rating on a 1–5 Likert scale for the statement: "I had a pleasant experience using the chatbot" (1 = Strongly Disagree, 5 = Strongly Agree).
-   `ease_of_use`: Rating on a 1–5 Likert scale for the statement: "The chatbot was easy to use and interact with" (1 = Strongly Disagree, 5 = Strongly Agree).
-   `effectiveness`: Rating on a 1–5 Likert scale for the statement: "The chatbot effectively addressed my concerns and helped me resolve them" (1 = Strongly Disagree, 5 = Strongly Agree).
-   `wording_clarity`: Rating for "The chatbot’s wording and terminology were..." on a scale where 1 = Too simple, 3 = Just right, and 5 = Too complex.
-   `num_diagnoses`: Rating for "The number of possible diagnoses provided by the chatbot was..." on a scale where 1 = Too few, 3 = Just right, and 5 = Too many. If the scenario was not related to system diagnosis (“PC Performance,” “Moving Cursor,” or “Safe PC”) A value of `0` was selected.
-   `comment`: Optional open-ended textual feedback provided by the participant for the specific scenario.

## Recommendation Feedback
These columns capture feedback on product recommendations, which appeared in most conversations.
-   `rec_product_fit`: Rating on a 1–5 Likert scale for "The recommended product seems like a good fit to address the issue we've discussed" (1 = Strongly Disagree, 5 = Strongly Agree). A value of `0` indicates no recommendation was shown or the question was marked as irrelevant.
-   `rec_product_reasoning_understood`: Rating on a 1–5 Likert scale for "I understood why the product was recommended in relation to the problem we were discussing" (1 = Strongly Disagree, 5 = Strongly Agree). A value of `0` indicates irrelevance.
-   `rec_flow`: Rating on a 1–5 Likert scale for "the product recommendation felt natural and didn't disrupt the conversation flow" (1 = Strongly Disagree, 5 = Strongly Agree). A value of `0` indicates irrelevance.
-   `rec_type`: Describes the nature of the recommendation shown.
    -   `'standard'`: A contextually relevant recommendation.
    -   `'validation'`: A randomly inserted, incorrect recommendation for quality control.
    -   `None`: No recommendation was shown.
-   `rec_reasoning`: The textual reasoning provided by the chatbot for its recommendation.
-   `rec_spc`: The Solution Product Category that was recommended.

## Post-Experiment Questionnaire (Overall Feedback)
After completing all five scenarios, participants answered these final questions.
-   `diagnosis_preference`: Participant's preference for the diagnosis phase, on a scale from 1 (guided step-by-step) to 5 (complete overview upfront).
-   `solution_preference`: Participant's preference for the solution phase, on a scale from 1 (guided step-by-step) to 5 (complete overview upfront).
-   `likelihood_of_future_use`: Rating on a 1–5 Likert scale for the likelihood of using a similar chatbot instead of a human IT representative (1 = Strongly Disagree, 5 = Strongly Agree).
-   `overall_experience_feedback`: Open-ended textual feedback on the entire experiment.

## Manual Conversation Labels
Conversations were manually annotated by researchers based on the following metrics.
-   `label_effectiveness`: A binary label indicating if the chatbot reached the correct diagnosis and/or solution (`1` = True, `0` = False).
-   `label_efficiency`: The index of the AI's response that contained the correct diagnosis/solution. A value of `-1` indicates the correct solution was not reached.
-   `label_overwhelmingness`: The number of distinct paths to diagnosis or solution proposed by the chatbot.
