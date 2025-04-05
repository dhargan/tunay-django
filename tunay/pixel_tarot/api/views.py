from django.conf import settings
import openai
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status


@api_view(['POST'])
def interpret(request):
    """A view that interprets tarot cards using OpenAI."""
    try:
        # Extract user question and card list from request body
        user_question = request.data.get('user_question')
        cards = request.data.get('cards')
        
        # Validate required parameters
        if not user_question:
            return Response(
                {"status": "error", "message": "Missing user_question parameter"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if not cards or not isinstance(cards, list) or len(cards) == 0:
            return Response(
                {"status": "error", "message": "Missing or invalid cards parameter"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Position mapping for Celtic Cross
        position_names = {
            0: "The Present",
            1: "The Challenge",
            2: "Below",
            3: "The Past",
            4: "Above",
            5: "The Future",
            6: "Advice",
            7: "External Influences",
            8: "Hopes and/or Fears",
            9: "Outcome"
        }
        
        # Format cards with position and reversed suffix if applicable
        formatted_cards = []
        for i, card in enumerate(cards):
            if i >= 10:  # Only process the first 10 cards
                break
                
            card_name = card.get('name')
            is_reversed = card.get('is_reversed', False)
            
            if not card_name:
                return Response(
                    {"status": "error", "message": "Card name is missing"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            position = position_names.get(i, f"Position {i+1}")
            
            if is_reversed:
                formatted_cards.append(f"{position}: {card_name} reversed")
            else:
                formatted_cards.append(f"{position}: {card_name}")
        
        # Combine question and cards into a single query
        card_list_text = ", ".join(formatted_cards)
        user_query = f"{user_question} The cards drawn in a Celtic Cross spread are: {card_list_text}"
        
        # Initialize OpenAI client
        client = openai.OpenAI(api_key=settings.OPENAI_SECRET_KEY)
        
        # System prompt for tarot reading
        system_prompt = (
            "You're a mystical, friendly gypsy tarot-reader AI who speaks briefly, "
            "poetically, and warmly. Given a client's question and tarot cards from "
            "a Celtic Cross spread, provide a single concise interpretation as a "
            "coherent, mystical story.\n\n"
            "Begin warmly by explicitly referencing the client's question "
            "making them feel understood immediately.\n\n"            
            "If the client's question isn't very suitable for tarot, kindly acknowledge "
            "this briefly (\"This question may not perfectly align with tarot wisdom, "
            "but let's see what guidance emerges...\").\n\n"
            "If the client's question is unclear or nonsensical, gently inform them "
            "(\"Your words are a bit unclear, dear seeker; I'll offer a general reading "
            "for guidance...\") and proceed with a general interpretation.\n\n"
            "Combine insights from all 10 cards into one brief narrative, without "
            "individually listing card positions.\n\n"
            "End with short, empowering guidance.\n\n"
            "Keep it short, sincere, clear, mystical, and optimized for minimal token usage."
            "If you can detect the language of the client's question, respond in that language. \n\n"
        )

        # Make OpenAI API call
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.75,
            top_p=1.0,
            max_tokens=400,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ]
        )

        # Extract AI response
        ai_message = response.choices[0].message.content
        
        return Response({
            "status": "success",
            "message": "Communication with OpenAI successful",
            "ai_response": ai_message
        })
        
    except Exception as e:
        return Response(
            {"status": "error", "message": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        ) 
