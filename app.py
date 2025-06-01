import os
import json
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import google.generativeai as genai
from datetime import datetime
from flask import Flask, render_template, request, jsonify

# Load environment variables
load_dotenv(override=True)
api_key = os.getenv('GOOGLE_API_KEY')

# Configure Gemini API
if not api_key:
    print("❌ No API key found - please ensure you have a GOOGLE_API_KEY in your .env file.")
    exit()

genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
}

app = Flask(__name__)

class StudentWebsiteAnalyzer:
    def __init__(self, url):
        self.url = url
        self.title = ""
        self.text = ""
        self.analysis = ""
        self.mcq_questions = []
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract title
            self.title = soup.title.string.strip() if soup.title else "No title found"
            
            # Extract main content
            main_content = ""
            
            # Try to find main content areas
            content_tags = soup.find_all(['main', 'article', 'section', 'div'], class_=lambda x: x and any(
                keyword in x.lower() for keyword in ['content', 'main', 'article', 'post', 'text', 'body']
            ))
            
            if content_tags:
                for tag in content_tags[:3]:
                    main_content += tag.get_text(separator=" ", strip=True) + " "
            else:
                if soup.body:
                    for irrelevant in soup.body(["script", "style", "img", "input", "nav", "footer", "header", "aside", "form", "button"]):
                        irrelevant.decompose()
                    main_content = soup.body.get_text(separator=" ", strip=True)
            
            # Clean and limit text
            self.text = main_content.strip()
            if len(self.text) > 4000:
                self.text = self.text[:4000] + "..."
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching website: {e}")
            self.title = "Error"
            self.text = "Failed to fetch content"
        except Exception as e:
            print(f"❌ Error processing website: {e}")
            self.title = "Error"
            self.text = "Failed to process content"
    
    def generate_student_analysis(self):
        if "Failed to" in self.text:
            self.analysis = "❌ Unable to analyze website due to content extraction error."
            return
        
        prompt = f"""
        You are helping students analyze websites. Please provide a comprehensive analysis of this website in the following format:

        🎯 **MAIN PURPOSE**
        [One clear sentence about what this website is for]

        📋 **KEY TOPICS COVERED**
        • [Topic 1]
        • [Topic 2]  
        • [Topic 3]
        • [Topic 4]

        🎓 **EDUCATIONAL VALUE**
        • [What students can learn]
        • [Academic subjects this relates to]
        • [Skills that can be developed]

        📊 **CONTENT TYPE**
        • [Type of content: articles, tutorials, news, etc.]
        • [Level: beginner, intermediate, advanced]
        • [Format: text, videos, interactive, etc.]

        🌟 **HIGHLIGHTS**
        • [Most interesting/important points]
        • [Unique features or resources]
        • [Why this site stands out]

        ⚡ **QUICK TAKEAWAYS**
        • [Key point 1]
        • [Key point 2]
        • [Key point 3]

        Website Title: {self.title}
        Content to analyze: {self.text}

        Please make it student-friendly, engaging, and easy to scan quickly.
        """
        
        try:
            response = model.generate_content(prompt)
            self.analysis = response.text.strip()
        except Exception as e:
            self.analysis = f"❌ Error generating analysis: {e}"

    def generate_mcq_questions(self, num_questions=5, difficulty="mixed"):
        """Generate MCQ questions based on the website content"""
        if "Failed to" in self.text:
            self.mcq_questions = []
            return
        
        difficulty_instruction = {
            "easy": "Create basic recall and understanding questions suitable for beginners.",
            "medium": "Create questions that require analysis and application of concepts.",
            "hard": "Create challenging questions that require critical thinking and synthesis.",
            "mixed": "Create a mix of easy, medium, and hard questions."
        }
        
        prompt = f"""
        Based on the following website content, create {num_questions} multiple choice questions to test student understanding.

        Requirements:
        - {difficulty_instruction.get(difficulty, difficulty_instruction["mixed"])}
        - Each question should have 4 options (A, B, C, D)
        - Only one correct answer per question
        - Questions should cover different aspects of the content
        - Make questions educational and relevant to the main topics
        - Avoid trick questions or overly obscure details
        - Include a brief explanation for the correct answer

        Format your response as a JSON array like this:
        [
          {{
            "question": "What is the main purpose of this website?",
            "options": {{
              "A": "Option A text",
              "B": "Option B text", 
              "C": "Option C text",
              "D": "Option D text"
            }},
            "correct_answer": "A",
            "explanation": "Brief explanation of why A is correct"
          }}
        ]

        Website Title: {self.title}
        Content: {self.text}

        Generate exactly {num_questions} questions in valid JSON format:
        """
        
        try:
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Clean up the response to extract JSON
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            
            # Parse JSON
            self.mcq_questions = json.loads(response_text)
            
            # Validate structure
            for i, q in enumerate(self.mcq_questions):
                if not all(key in q for key in ['question', 'options', 'correct_answer', 'explanation']):
                    raise ValueError(f"Question {i+1} missing required fields")
                if not all(option in q['options'] for option in ['A', 'B', 'C', 'D']):
                    raise ValueError(f"Question {i+1} missing required options")
                    
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error: {e}")
            self.mcq_questions = [{"error": "Failed to parse MCQ questions - invalid JSON format"}]
        except Exception as e:
            print(f"❌ Error generating MCQ questions: {e}")
            self.mcq_questions = [{"error": f"Failed to generate MCQ questions: {str(e)}"}]

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    # Add protocol if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        analyzer = StudentWebsiteAnalyzer(url)
        analyzer.generate_student_analysis()
        
        # Convert analysis to HTML format for frontend
        html_analysis = analyzer.analysis.replace('\n', '<br>')
        
        return jsonify({
            "url": url,
            "title": analyzer.title,
            "date": datetime.now().strftime('%Y-%m-%d at %H:%M'),
            "analysis": html_analysis
        })
        
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500

@app.route('/generate-mcq', methods=['POST'])
def generate_mcq():
    """New endpoint for generating MCQ questions"""
    data = request.get_json()
    url = data.get('url')
    num_questions = data.get('num_questions', 5)
    difficulty = data.get('difficulty', 'mixed')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    # Validate parameters
    try:
        num_questions = int(num_questions)
        if num_questions < 1 or num_questions > 10:
            num_questions = 5
    except (ValueError, TypeError):
        num_questions = 5
    
    if difficulty not in ['easy', 'medium', 'hard', 'mixed']:
        difficulty = 'mixed'
    
    # Add protocol if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        analyzer = StudentWebsiteAnalyzer(url)
        analyzer.generate_mcq_questions(num_questions, difficulty)
        
        return jsonify({
            "url": url,
            "title": analyzer.title,
            "questions": analyzer.mcq_questions,
            "total_questions": len(analyzer.mcq_questions),
            "difficulty": difficulty,
            "date": datetime.now().strftime('%Y-%m-%d at %H:%M')
        })
        
    except Exception as e:
        return jsonify({"error": f"MCQ generation failed: {str(e)}"}), 500

@app.route('/analyze-with-mcq', methods=['POST'])
def analyze_with_mcq():
    """Combined endpoint for both analysis and MCQ generation"""
    data = request.get_json()
    url = data.get('url')
    num_questions = data.get('num_questions', 5)
    difficulty = data.get('difficulty', 'mixed')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    # Validate parameters
    try:
        num_questions = int(num_questions)
        if num_questions < 1 or num_questions > 10:
            num_questions = 5
    except (ValueError, TypeError):
        num_questions = 5
    
    if difficulty not in ['easy', 'medium', 'hard', 'mixed']:
        difficulty = 'mixed'
    
    # Add protocol if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        analyzer = StudentWebsiteAnalyzer(url)
        analyzer.generate_student_analysis()
        analyzer.generate_mcq_questions(num_questions, difficulty)
        
        # Convert analysis to HTML format for frontend
        html_analysis = analyzer.analysis.replace('\n', '<br>')
        
        return jsonify({
            "url": url,
            "title": analyzer.title,
            "date": datetime.now().strftime('%Y-%m-%d at %H:%M'),
            "analysis": html_analysis,
            "questions": analyzer.mcq_questions,
            "total_questions": len(analyzer.mcq_questions),
            "difficulty": difficulty
        })
        
    except Exception as e:
        return jsonify({"error": f"Analysis with MCQ failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)
