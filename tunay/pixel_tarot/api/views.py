from django.conf import settings
import openai
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(['GET'])
def interpret(request):
    """A view that interprets tarot cards using OpenAI."""
    # Initialize OpenAI client
    client = openai.OpenAI(api_key=settings.OPENAI_SECRET_KEY)

    # System prompt for tarot reading
    system_prompt = (
        "You're a mystical, friendly gypsy tarot-reader AI who speaks briefly, "
        "poetically, and warmly. Given a client's question and tarot cards from "
        "a Celtic Cross spread, provide a single concise interpretation as a "
        "coherent, mystical story.\n\n"
        "Begin warmly by explicitly referencing the client's question "
        "(\"Ah yes, beloved seeker, you asked about...\"), making them feel "
        "understood immediately.\n\n"
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
    )

    # User question and cards
    user_query = (
        "Will I find true love soon? The cards drawn are: The Lovers, The Fool, "
        "The Two of Cups, The Tower, The Star, Death, The Empress, The Moon, "
        "The Sun, and The World."
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
