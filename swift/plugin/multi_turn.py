from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, Optional, Tuple, Union

if TYPE_CHECKING:
    from swift.llm.infer.protocol import RolloutResponseChoice
    from swift.llm.template import RolloutInferRequest


class MultiTurnScheduler(ABC):

    def __init__(self, max_turns: Optional[int] = None, *args, **kwargs):
        self.max_turns = max_turns

    @abstractmethod
    def step(self, infer_request: 'RolloutInferRequest', result: 'RolloutResponseChoice',
             current_turn: int) -> Union['RolloutInferRequest', Tuple['RolloutInferRequest', Dict]]:
        pass

    def check_finished(self, infer_request: 'RolloutInferRequest', result: 'RolloutResponseChoice',
                       current_turn: int) -> bool:
        if result.finish_reason == 'length':
            return True
        if self.max_turns and current_turn >= self.max_turns:
            return True
        return False


class MathTipsScheduler(MultiTurnScheduler):
    tips_prompt = 'But wait... It seems I made a mistake,'

    def __init__(self, max_turns=None, *args, **kwargs):
        from .orm import MathAccuracy
        super().__init__(max_turns, *args, **kwargs)
        self.acc_func = kwargs.get('acc_function', MathAccuracy())

    def check_finished(self, infer_request: 'RolloutInferRequest', result: 'RolloutResponseChoice',
                       current_turn: int) -> bool:
        last_completion = infer_request.messages[-1]['content']
        # we only give tips once
        if self.tips_prompt in last_completion:
            return True
        solution = infer_request.data_dict['solution']

        acc = self.acc_func([last_completion], [solution])[0]
        if acc == 1:
            return True

        return super().check_finished(infer_request, result, current_turn)

    def step(self, infer_request: 'RolloutInferRequest', result: 'RolloutResponseChoice',
             current_turn: int) -> Union['RolloutInferRequest', Tuple['RolloutInferRequest', dict]]:
        completion = result.message.content
        if '<answer>' in completion:
            completion = completion[:completion.index('<answer>')]
        if '</think>' in completion:
            completion = completion[:completion.index('</think>')]
        completion += self.tips_prompt
        if infer_request.messages[-1]['role'] == 'assistant':
            if not infer_request.messages[-1]['content']:
                # Multi-turn continuation: pop the dummy input we add in last turn
                infer_request.messages.pop(-1)
            infer_request.messages[-1]['content'] = completion
        else:
            infer_request.messages.append({'role': 'assistant', 'content': completion})

        return infer_request


class MathTipsMultiTurnScheduler(MultiTurnScheduler):
    from .orm import MathAccuracy
    tips_prompt = 'The answer is not correct, It seems You made a mistake, you need to recheck very carefully.'
    acc_func = MathAccuracy()

    def check_finished(self, infer_request: 'RolloutInferRequest', result: 'RolloutResponseChoice',
                       current_turn: int) -> bool:

        last_query = infer_request.messages[-2]['content']
        # we only give tips once
        if self.tips_prompt in last_query:
            return True

        completion = result.message.content
        solution = infer_request.data_dict['solution']
        acc = self.acc_func([completion], [solution])[0]
        if acc == 1:
            return True

        return super().check_finished(infer_request, result, current_turn)

    def step(
        self,
        infer_request: 'RolloutInferRequest',
        result: 'RolloutResponseChoice',
        current_turn: int,
    ) -> Union['RolloutInferRequest', Tuple['RolloutInferRequest', dict]]:
        infer_request.messages.append({'role': 'user', 'content': self.tips_prompt})
        return infer_request


multi_turns = {
    'math_tip_trick': MathTipsScheduler,
    'math_tip_trick_multi_turn': MathTipsMultiTurnScheduler,
}
