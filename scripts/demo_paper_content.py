"""Content of the SYNTHETIC demonstration paper (see build_demo_pdf.py).

This is NOT a real study. It exists to test PDF extraction, sectioning,
traceability and report generation against known ground truth. Numbers are
illustrative placeholders, references are explicit placeholders, and nothing
here may be cited or used as evidence about financial markets.
"""

TITLE = "Transferring Pricing Kernels Across Equity Markets: A Synthetic Demonstration Paper"
AUTHORS = "Demo Author One and Demo Author Two (synthetic test document)"
ABSTRACT = (
    "We study whether a stochastic discount factor estimated on a data-rich equity market can improve "
    "asset pricing in markets with short return histories. We pre-train a neural network SDF on United "
    "States stocks and fine-tune it on 24 developed and emerging markets. In this synthetic example, the "
    "transferred SDF lowers out-of-sample pricing errors by 14% relative to locally estimated models, "
    "and the gains concentrate in emerging markets. We interpret the results through partial market "
    "integration: common risk premia can be learned where data are plentiful and adapted where they are scarce.")

FOOTNOTE = ("* Synthetic demonstration document generated for software testing. All numbers are illustrative "
            "and do not describe real data.")

# (heading or None, [paragraphs]) ; heading strings include numbering.
SECTIONS = [
    ("1 Introduction", [
        "Estimating the stochastic discount factor (SDF) is central to empirical asset pricing, yet many "
        "international equity markets offer only short and noisy return histories. Local estimation in such "
        "markets is prone to overfitting, and the resulting pricing kernels are unstable out of sample. This "
        "paper asks whether knowledge learned from a data-rich market can be transferred to data-scarce markets "
        "without imposing full market integration.",
        "Our contribution is to cast cross-market SDF estimation as a transfer learning problem. Unlike prior "
        "studies that either pool all countries or estimate each market separately [1], we pre-train a common "
        "representation and allow country-specific adaptation. This intermediate approach nests the integrated "
        "and segmented benchmarks as special cases.",
        "The paper is also loosely related to work on return predictability [3], although we do not forecast "
        "returns and our evaluation focuses on pricing errors rather than predictive accuracy.",
    ]),
    ("2 Related Literature", [
        "A large literature estimates SDFs with machine learning in a single market [1], and a separate "
        "literature tests international asset pricing models under integration and segmentation [2]. We "
        "build on both strands but differ in that the degree of integration is learned from the data through "
        "the fine-tuning step.",
    ]),
    ("3 Theoretical Framework", [
        "We start from the fundamental pricing equation E[M(t+1) R(t+1)] = 0 for excess returns R, where M is "
        "the SDF. Following standard practice, we project the SDF on traded portfolios, M(t+1) = 1 - w(t)' F(t+1), "
        "where the weights w(t) depend nonlinearly on firm characteristics.",
        "The economic mechanism is partial integration. If markets share common sources of systematic risk, "
        "the mapping from characteristics to SDF weights is similar across countries, so parameters learned "
        "in the source market are informative about the target market. Country-specific frictions, such as "
        "segmentation or currency risk, imply deviations that the fine-tuning step must capture.",
    ]),
    ("4 Data", [
        "Our sample consists of monthly returns for common stocks in 24 developed and emerging markets "
        "between January 1995 and December 2022. Returns are measured in U.S. dollars and in excess of the "
        "one-month U.S. Treasury bill rate.",
        "We define 30 firm characteristics, including size, book-to-market, momentum and profitability, "
        "measured with a six-month reporting lag to avoid look-ahead bias. Characteristics are ranked "
        "cross-sectionally within each country and month and mapped to the interval [-0.5, 0.5]. We exclude "
        "stocks below the 10th percentile of market capitalization in each country.",
    ]),
    ("5 Empirical Methodology", [
        "We estimate the SDF weights by minimizing the generalized method of moments objective implied by "
        "the pricing equation, using a feed-forward neural network with three hidden layers.",
    ]),
    ("5.1 Pre-training and fine-tuning", [
        "In the pre-training step the network is trained on U.S. data from 1995 to 2010. In the fine-tuning "
        "step, the network is re-estimated on each target market with a penalty on deviations from the "
        "pre-trained weights. Hyperparameters, including the penalty strength, are chosen on a validation "
        "sample from 2011 to 2014, and all results are reported for the out-of-sample period from 2015 to 2022.",
        "Identification of the transfer benefit comes from comparing models that differ only in their "
        "initialization and penalty, holding the data, architecture and evaluation period fixed. Standard "
        "errors are computed with a block bootstrap over months.",
    ]),
    ("6 Empirical Results", [
        "Table 1 summarizes out-of-sample pricing performance. We find that the transferred SDF reduces the "
        "root-mean-squared pricing error by 14% relative to the locally estimated SDF, with a bootstrap "
        "t-statistic of 2.9.",
        "The gains are concentrated in emerging markets, where pricing errors fall by 21%, compared with 8% "
        "in developed markets. The tangency portfolio implied by the transferred SDF earns an annualized "
        "Sharpe ratio of 0.94 out of sample, compared with 0.61 for the local model.",
        "These patterns are consistent with partial integration: markets with lower measured integration "
        "benefit less from the U.S. source representation.",
    ]),
    ("7 Robustness and Limitations", [
        "The results are robust to using Japan instead of the United States as the source market and to "
        "alternative network depths. However, the benefits disappear for the three markets with the lowest "
        "integration scores.",
        "Our analysis does not account for transaction costs, and the out-of-sample period is relatively "
        "short. We also do not address multiple testing across the specifications we report.",
    ]),
    ("8 Conclusion", [
        "Transfer learning offers a practical middle ground between fully integrated and fully segmented "
        "SDF estimation. Future research could examine whether the learned representation transfers across "
        "asset classes, such as corporate bonds or currencies.",
    ]),
    ("References", [
        "[1] Synthetic Reference One. Placeholder title on machine-learning SDF estimation. Not a real publication.",
        "[2] Synthetic Reference Two. Placeholder title on international asset pricing tests. Not a real publication.",
        "[3] Synthetic Reference Three. Placeholder title on return predictability. Not a real publication.",
    ]),
    ("A Additional Details", [
        "The validation sample is also used to select the learning rate and the early-stopping epoch. All "
        "random seeds are fixed so the synthetic results can be reproduced exactly.",
    ]),
]

TABLE_CAPTION = "Table 1: Out-of-sample pricing errors (synthetic illustration)"
TABLE_ROWS = [
    ["Model", "RMSE", "Sharpe", "t-stat"],
    ["Local SDF", "1.00", "0.61", "-"],
    ["Pooled SDF", "0.93", "0.78", "1.7"],
    ["Transferred SDF", "0.86", "0.94", "2.9"],
]
