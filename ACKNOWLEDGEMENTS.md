# Acknowledgements and Open Source Notices

This project relies on third-party open-source software, models, datasets, and cloud services. We gratefully acknowledge the contributions of the original authors and maintainers. Below is a comprehensive list of these dependencies along with their respective licensing terms.

---

## 1. Custom and Gated AI Model Licenses
The following machine learning models are used under specialized, custom community licenses provided by their respective creators. By using this project, you agree to comply with their specific terms:

*   **Gemma / gemma2:2b** 
    *   *License:* Google Gemma Terms of Use
    *   *Notice:* Subject to the Google Gemma restrictive terms. https://ai.google.dev/gemma/prohibited_use_policy
*   **Llama 3.2:3b**
    *   *License:* Meta Llama 3.2 Community License
    *   *Notice:* Applications built using this model must prominently display "Built with Meta Llama".https://developer.meta.com/ai/llama3_2/license/
*   **Qwen3 / qwen3:4b**
    *   *License:* Alibaba Qwen License Agreement
    *   *Notice:* Subject to Alibaba's commercial user-count caps and distribution guidelines.

---

## 2. Text Corpora and Datasets
*   **Scripture Corpus**
    *   *License:* Public Domain
    *   *Notice:* The scripture text utilized in this project is sourced entirely from Public Domain translations. It is free of active copyright restrictions and may be used, redistributed, or modified without limitation. The repository's original project material is licensed separately under CC BY 4.0 in `LICENSE.txt`.
---

## 3. Hugging Face Models
The following model weights are downloaded dynamically or utilized via Hugging Face and are governed by individual open-source licenses:

*   `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (Apache 2.0)
*   `cross-encoder/ms-marco-MiniLM-L6-v2` (Apache 2.0)
*   `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank` (MIT / Apache 2.0)

---

## 4. Apache License 2.0 Dependencies
The following libraries and platforms are licensed under the Apache License, Version 2.0. A copy of this license can be found at `http://apache.org`.

*   **Backend & Orchestration:** fastapi, uvicorn[standard], pydantic-settings, transformers, litellm, google-adk
*   **Databases & Vector Search:** PostgreSQL, milvus-lite, pymilvus, Milvus
*   **Monitoring & Instrumentation:** codecarbon

---

## 5. MIT License Dependencies
The following libraries and tools are licensed under the MIT License. Their original copyright notices are preserved within their respective installations.

*   **Backend Frameworks & Tools:** Ollama(This project utilizes [Ollama](https://ollama.com) to run large language models locally. 
Model weights are subject to their respective creators' licenses (e.g., Meta Llama 3 Community License).)), python-dotenv, pyjwt, httpx, mcp, llmlingua, pytest
*   **Frontend Ecosystem:** react, react-dom, lucide-react, tailwindcss, @tailwindcss/vite, vite, @vitejs/plugin-react, typescript, @types/react, @types/react-dom

---

## 6. BSD & Other Open Licenses
*   **numpy** (BSD-3-Clause License)
*   **psutil** (BSD-3-Clause License)
*   **asyncpg** (Dual-licensed under the Apache 2.0 or MIT License)
*   **redis** (Subject to the Redis Source Available License / Server Side Public License; ensure compliance based on the specific version or fork used).

---

## 7. Runtime Environments and External Cloud APIs
This project requires the following environments to run, and interacts with third-party cloud services that require individual user keys and adherence to independent Terms of Service:

*   **Python 3.10+** (Python Software Foundation License)
*   **Node.js 18+** (MIT-based licenses)
*   **Google Gemini API** (Subject to the Google APIs Terms of Service)
