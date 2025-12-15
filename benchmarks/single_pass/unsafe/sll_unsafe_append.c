struct Node {
    int value;
    struct Node *next;
};    

void sll_unsafe_append(struct Node **head, int key) {
    struct Node *n;
    struct Node *curr;
    struct Node *next;
    int tmp_key;

    n = malloc(sizeof(struct Node)); //0
    n->value = key;

    curr = *head;

    if(curr != 0) { //3
        next = curr->next; //4
        while(next != 0) {
            curr = next; //6
            next = curr->next; //7
        }    
        next->next = n; //8
    }    
}    