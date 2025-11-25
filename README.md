# DeepScientist: Advancing Frontier-Pushing Scientific Findings Progressively 

<div align="center">
  
[![GitHub stars](https://img.shields.io/github/stars/ResearAI/DeepScientist)](https://github.com/ResearAI/DeepScientist/stargazers) 
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/release/python-380/) 
[![arXiv](https://img.shields.io/badge/arXiv-2509.26603-b31b1b.svg)](https://arxiv.org/abs/2509.26603)
[![Homepage](https://img.shields.io/badge/Homepage-ai--researcher.net-green.svg)](http://ai-researcher.net)

</div>

![image.png](Figure/deepscientist_figure.png)

---

# 🔥 Featured News

- [2025.10.1] The call for papers is now open for [the first International Conference on AI Scientist (ICAIS)](https://icais.ai), to be held in Beijing!

---

We're excited to share DeepScientist, the first large-scale empirical evidence that an AI can progressively surpass the human SOTA on frontier scientific tasks. In a striking demonstration in the highly competitive field of AI text detection, DeepScientist achieved progress in just two weeks that is comparable to three years of cumulative human research. The DeepScientist system overcomes this by demonstrating goal-oriented, continuous, and iterative scientific discovery without human intervention, marking a significant step toward AI becoming a true partner in research.

![image.png](Figure/DeepScientist.png)

We have now demonstrated that AI can genuinely push the frontier forward across multiple, diverse domains. On the popular research topic of AI text detection, DeepScientist autonomously generated 2,472 unique research ideas, implemented 600 of the most promising hypotheses, and ultimately produced methods that increased the AUROC score by 7.9% on the RAID dataset while simultaneously reducing inference latency. This capability extends far beyond a single breakthrough. When tasked with the highly complex challenge of "Agent Failure Attribution," DeepScientist independently conceived of and proposed a novel method named A2P (Abduction-Action-Prediction). Its core innovation was to elevate the task from simple pattern recognition to structured causal reasoning. This new method achieved a score of 47.46 on the "algorithm-generated" setting of the Who&When benchmark, a massive 183.7% improvement over the human SOTA baseline. These achievements prove DeepScientist can produce discoveries with lasting impact and systematically advance the technological frontier in multiple fields.

![image.png](Figure/result.png)

### Open Source Plan
Our entire open source plan will be divided into four phases.

#### Phase 1: Application-Based Access 
To ensure safety, we will invite a small group of users to try DeepScientist. If you have a task you're ready to explore, please fill out our [Waitlist Form](https://forms.gle/8FnGgqgBVEKv3q6a7). We will collaborate with you to further refine DeepScientist.

#### Phase 2: Foundational Components Release

**(UPDATE) This stage has been completed. We are providing the [http://deepscientist.cc](http://deepscientist.cc) website and the [DeepScientist-CLI](https://github.com/ResearAI/DeepScientist-CLI) code, which are now open for use by the first 30 invited users.**

After ensuring safety, we will open-source our foundational components. At this stage, you can immediately start building your own DeepScientist or replicating our work (perhaps an "Open-DeepScientist," which we strongly encourage!):


- Your implementation could very well be more elegant and efficient than ours. We admit that our implementation of components and workflows still contains some unpolished code and design.

- Don't limit your imagination. DeepScientist is just one small step. Automating scientific discovery with AI is an incredibly exciting field with vast room for exploration!

#### Phase 3: Experimental Data Release (Expected after November)
We will open-source all ~5,000 hypotheses and ~1,100 experimental logs. This will be the first time such a large-scale dataset of AI-generated experimental results has been made public.

#### Phase 4: DeepScientist Source Code Release
We will act responsibly, conducting long-term testing and adjustments to prevent any potential harm to human research. Following this, we will release the core architecture of the DeepScientist code to foster community development.


### Some Thoughts

**If you find the following comments helpful, feel free to give a star to this repo, by [Yixuan Weng](https://scholar.google.com/citations?hl=zh-CN&user=O1XsDEMAAAAJ&view_op=list_works&sortby=pubdate).**


###### Comment 1

* Q: Your previous project was [CycleResearcher](https://github.com/zhu-minjun/Researcher). Why did you call this new one `DeepScientist` instead of `DeepResearcher`?
* A: Back in September 2024, I had already planned to name my current work “DeepResearcher,” similar to [DeepReviewer](https://github.com/zhu-minjun/Researcher). However, OpenAI later took over that name. So, I decided to call my project `DeepScientist`.


###### Comment 2

* Q: When will you open-source it?
* A: I will open-source it only after ensuring sufficient safety, because I’m still not entirely certain that the benefits of `DeepScientist` to academia outweigh its potential risks. Therefore, I have to take a cautious approach.
* Q: Why are you taking a phased open-source strategy?
* A: Because the community is extremely enthusiastic—almost everyone can’t wait for me to open-source it! I plan to spend my National Day and Mid-Autumn Festival holidays (in China, this is the longest public holiday in 2025) revising the code, so the community can experience the system earlier and explore how it might accelerate scientific discovery across different fields. Thanks to the support of [Zhongguancun Academy](http://bjzgca.edu.cn/), we will be able to provide the full DeepScientist system **free of charge** to the community. If you’re interested, you can sign up early using the [Waitlist Form](https://forms.gle/8FnGgqgBVEKv3q6a7).


###### Comment 3

* Q: Do you believe there is a Scaling Law for AI-driven scientific discovery?
* A: I firmly believe that AI-driven scientific discovery follows its own Scaling Law. But it’s not an isolated phenomenon—it’s a natural extension and amplification of the accelerating pace of human discovery. Throughout history, the speed of scientific progress has continuously increased, and in modern times this acceleration is especially tangible. Ever since middle school, I loved playing *Sid Meier’s Civilization*, where knowledge and technology accumulation leads to faster “Eureka moments.” I believe we are now entering a real-world “Eureka Era” driven by AI.



###### Comment 4

* Q: At present, so-called “AI scientists” seem more like “high-throughput trial-and-error machines” rather than true “discoverers” with deep insights. How can we improve their scientific intuition?
* A: First, as model capabilities grow, I can already sense improvements in their ability to identify limitations in scientific questions. Early on, with DeepSeek-R1, its observations were very superficial. But after the release of Qwen-3-235B-Thinking-2507, its insight and hypothesis-generation capabilities clearly improved. (In my view, only models stronger than this Qwen-3-235B version are capable of generating truly valuable discoveries.) RLVR is a promising direction, but it comes with challenges: high costs and low training efficiency (roughly 1000 GPU hours to produce just one useful sample).


###### Comment 5

* Q: The total cost of this research is about $100,000. Compared to funding a human PhD student for a similar research cycle, do you think this is cost-effective at the current stage?
* A: I think both have their strengths. Failure is the mother of success, and the biggest advantage of AI is its ability to explore continuously without fatigue. On one hand, we can rely on AI to try many different strategies—even discovering that a certain approach fails in a field is itself a meaningful finding. On the other hand, this is just the beginning. In the coming years, AI costs will decrease significantly due to both improved capabilities and cheaper reasoning.



###### Comment 6

* Q: One of the most exciting findings in your paper is the “near-linear relationship” between computational resources and research output. Do you predict this trend will continue indefinitely with more GPUs, or will it soon hit a bottleneck? What might that next bottleneck be?
* A: I don’t think it will continue indefinitely. We are about to hit a bottleneck. The next bottleneck will be “exploration efficiency,” not “exploration scale.” Right now, most compute is wasted on low-value explorations. In the future, the challenge is to avoid such low-value work. While DeepScientist occasionally discovers new methods to improve performance through trial and error, the gains are often marginal. True breakthroughs will only come when we can perform large-scale, high-value exploration.


###### Comment 7

* Q: Are there any other surprises?
* A: Yes! In early October, we will both fully open-source a tool. I believe every researcher will be interested in it—it significantly enhances DeepScientist’s demonstration capabilities.


---

# 📰 Latest Work


* **Survey | How Far Are AI Scientists from Changing the World?**
    * *Source:* arXiv Publication (Jul 2025)
    * *Link:* [Paper](https://arxiv.org/pdf/2507.23276)
    * *Link:* [Resource](https://github.com/ResearAI/Awesome-AI-Scientist)

* **Position Paper | AI Scientists Fail Without Strong Implementation Capability**
    * *Source:* arXiv Publication (Jun 2025)
    * *Link:* [Paper](https://arxiv.org/pdf/2506.01372)

* **Launch | Airaxiv. Your Gateway to AI-Generated Research!**
    *   *Source:* Airaxiv Website
    *   *Link:* [Website](https://airaxiv.com/)

* **Research Paper | DeepReview: Improving LLM-based Paper Review with Human-like Deep Thinking Process**
    * *Source:* aclanthology (ACL 2025)
    * *Link:* [Paper](https://aclanthology.org/2025.acl-long.1420/)
    * *Link:* [Code](https://github.com/zhu-minjun/Researcher/)
 
* **Research Paper | CycleResearcher: Improving Automated Research via Automated Review**
    * *Source:* OpenReview (ICLR 2025)
    * *Link:* [Paper](https://openreview.net/pdf?id=bjcsVLoHYs)
    * *Link:* [Code](https://github.com/zhu-minjun/Researcher/)



## 💬 Discussion Forums

Join the conversation and exchange ideas in these online communities:

**AI Scientist Research Discussion Group:** [![Platform](https://img.shields.io/badge/WeChat-07C160?style=for-the-badge&logo=wechat&logoColor=white)]() 

If you’re interested in AI Scientist, you can add **nauhcutnil** on WeChat to be invited to the AI Scientist discussion group. Please include the note **“AIScientist Wechat Group”** when sending your friend request.

  


```
@article{weng2025deepscientist,
  title={DeepScientist: Advancing Frontier-Pushing Scientific Findings Progressively},
  author={Weng, Yixuan and Zhu, Minjun and Xie, Qiujie and Sun, Qiyao and Lin, Zhen and Liu, Sifan and Zhang, Yue},
  journal={arXiv preprint arXiv:2509.26603},
  year={2025}
}
```
