import copy
import random
from functools import partialmethod
from typing import Dict

import numpy as np
import torch
from omegaconf import OmegaConf

from src.abstract import BaseConstruct
from src.net import QMixer
from src.registry import register_construct


@register_construct
class BaseQMIX(BaseConstruct):
    """
    Base implementation of QMIX: Monotonic Value Function Factorisation
    for Deep Multi-Agent Reinforcement Learning

    Args:
        :param [hypernet_conf]: hypernetwork configuration
        :param [mixer_conf]: mixer head configuration

    Internal State:
        :param [eval_mixer]: evaluation mixing network instance
        :param [target_mixer]: frozen instance of network used for target calculation

    """

    def __init__(self, hypernet_conf: OmegaConf, mixer_conf: OmegaConf) -> None:
        self._hypernet_conf = hypernet_conf
        self._mixer_conf = mixer_conf

        # internal attrs
        self._eval_mixer = None
        self._target_mixer = None
        self._criterion = None

    def _rnd_seed(self, *, seed: int = None):
        """set random generator seed"""
        if seed:
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed(seed)
            np.random.seed(seed)
            random.seed(seed)

    def ensemble_construct(
        self, n_agents: int, observation_dim: int, state_dim: int, *, seed: int = None
    ) -> None:
        self._rnd_seed(seed=seed)

        # ---- ---- ---- ---- ---- ---- #
        # ---  -- Prepare Mixers --- -- #
        # ---- ---- ---- ---- ---- ---- #

        hypernet_embed_dim = self._hypernet_conf.embedding_dim
        mixer_embed_dim = self._mixer_conf.embedding_dim
        n_hypernet_layers = self._hypernet_conf.n_layers
        self._eval_mixer = QMixer(
            hypernet_embed_dim=hypernet_embed_dim,
            mixer_embed_dim=mixer_embed_dim,
            n_hypernet_layers=n_hypernet_layers,
        )
        self._eval_mixer.integrate_network(n_agents, state_dim, seed=seed)

        # deepcopy eval network structure for frozen mixer networl
        self._target_mixer = copy.deepcopy(self._eval_mixer)

        # ---- ---- ---- ---- ---- ---- #
        # --- - Prepare Criterion -- -- #
        # ---- ---- ---- ---- ---- ---- #

        self._criterion = torch.nn.MSELoss()

    def factorize_q_vals(
        self, agent_qs: torch.Tensor, states: torch.Tensor, use_target: bool = False
    ) -> torch.Tensor:
        """takes batch and computes factorised q-value"""
        factorized_qs = (
            self._target_mixer(agent_qs, states)
            if use_target
            else self._eval_mixer(agent_qs, states)
        )
        return factorized_qs

    def synchronize_target_net(self, tau: float = 1.0):
        """copy weights from eval net to target net using tau temperature.

        for tau = 1.0, this performs a hard update.
        for 0 < tau < 1.0, this performs a soft update.
        """
        for target_param, eval_param in zip(
            self._target_mixer.parameters(), self._eval_mixer.parameters()
        ):
            target_param.data.copy_(
                tau * eval_param.data + (1 - tau) * target_param.data
            )

    def parameters(self):
        """return hypernet and mixer optimization params"""
        return self._eval_mixer.parameters()

    def move_to_cuda(self):
        """move models to cuda device"""
        self._eval_mixer.cuda()
        self._target_mixer.cuda()

    def calculate_loss(self, batch: Dict[str, torch.Tensor]) -> torch.Tensor:
        """use partial methods to calcualte criterion loss between eval and target"""
        pass

    # ---- ---- ---- ---- ---- #
    # --- Partial Methods ---- #
    # ---- ---- ---- ---- ---- #

    factorize_eval_q_vals = partialmethod(factorize_q_vals, use_target=False)
    factorize_target_q_vals = partialmethod(factorize_q_vals, use_target=True)
