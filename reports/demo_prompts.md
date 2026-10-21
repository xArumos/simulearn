# Demo cheat sheet: adult lines to type

All lines below are **invented** in the style of the CHILDES transcripts (no transcript text), so they are safe to show and commit.

**How the training data sounds:** adults talk in short, casual lines, often a quick comment plus a question ("oh nice. what's that one?"). Lowercase is fine, because the transcripts are mostly lowercase. Use **New conversation** between scenarios. Each scenario works best as 3–5 lines typed in order.

---

## 1. Toy play (most common setting)
1. what are you making over there?
2. ooh. is that a house or a garage?
3. who's gonna live in it?
4. uh oh, it fell down. what happened?
5. can you build it taller this time?

## 2. Mealtime
1. okay, sit down please. it's time to eat.
2. do you want milk or juice?
3. what did you have for lunch at school today?
4. two more bites and then you can be done.
5. did you like the carrots?

## 3. Picture book
1. let's read this one. what do you think this story is about?
2. look at that dog. what's he doing?
3. why do you think he's sad?
4. what do you think happens next?
5. should we turn the page?

## 4. Researcher / picture task (like the museum-lab sessions)
1. hi! can you tell me your name?
2. okay, I'm gonna show you some pictures. what's this one?
3. good. and what is the girl doing here?
4. is she happy or sad?
5. anything else you see in this picture?

## 5. Made-up-word game (unreliable live, so skip it or use it as a talking point)
1. this is a blick.
2. now there's another one. there are two of them. there are two...

In a pre-meeting test the fine-tuned model said "I can't see it!" and then "what?". That's a reasonable reply: a text-only model can't see the toy being shown. In the real transcripts the child can see it.

## 6. Pretend phone call
1. ring ring! hello?
2. who is this?
3. oh hi! what are you doing today?
4. okay, bye bye!

## 7. Feelings and "why" questions (open-ended, for longer replies)
1. you look tired. did you sleep okay?
2. what's your favorite thing to do outside?
3. why do you like that one the best?
4. what would you do if you saw a lion?

## 8. Wait time (silence tags)
You can type a pause into the adult's line, as in the data: the tag goes at the **start** of the line.
- `<SILENCE FOR 4 SECONDS> so... what do you wanna play next?`
- `<SILENCE FOR 3 SECONDS> do you know what this is called?`

The fine-tuned model sometimes starts its reply with a pause too (shown as *(thinking…)* / *(…pauses…)*).

---

## Tips for the live demo
- **Good contrast:** open "what / why" questions (scenarios 3, 4, 7). The untrained model lectures or asks the adult questions back; the fine-tuned one answers in a few words, like a child.
- **Expected weakness:** the fine-tuned model sometimes just says "I don't know." That's the known issue on the "What's not working yet" slide. Point it out, don't hide it.
- **Fairer comparison:** tick "stronger talk like a real child prompt" to show that even a well-prompted untrained model stays polite and adult-like ("thanks for asking!").
- Replies are random (sampling), so the same line can give a different answer each time. That's normal, and it matches how we evaluate.
- Around 4 seconds per message is normal.
- **Tested before the meeting** (results vary): "look at that dog. what's he doing?" → fine-tuned: "he's looking through a hole in his window."; untrained: "The dog looks happy and wagging his tail! He seems to be playing fetch…". "what do you think this story is about?" → fine-tuned: "uh I don't know."; untrained asked for "a specific story or passage". "did you sleep okay?" → fine-tuned: "yeah."; untrained: a run-on about lunch.
- Lines that refer to a picture or object work less well, since neither model can see anything. Lines about the child's own life (school, food, pets, play) work best.
