migrate((app) => {
  // Protocol storage is never readable/writable through collection APIs or SQL.
  for (const definition of [
    {name: 'identity_requests', fields: [
      new TextField({name:'email',required:true,max:254}),
      new TextField({name:'challenge',required:true,max:128}),
      new TextField({name:'code_hash',max:128}),
      new TextField({name:'account_key_hash',max:128}),
      new RelationField({name:'subject',collectionId:app.findCollectionByNameOrId('users').id,maxSelect:1}),
      new NumberField({name:'expires',required:true}),
      new NumberField({name:'attempts'}),
      new BoolField({name:'used'})]},
    {name: 'identity_sessions', fields: [
      new TextField({name:'token_hash',required:true,max:128}),
      new RelationField({name:'subject',required:true,collectionId:app.findCollectionByNameOrId('users').id,maxSelect:1}),
      new TextField({name:'account_key_hash',required:true,max:128}),
      new NumberField({name:'expires',required:true}),
      new NumberField({name:'idle_expires',required:true}),
      new BoolField({name:'revoked'})], indexes:['CREATE UNIQUE INDEX idx_identity_token ON identity_sessions (token_hash)']}
  ]) {const collection=new Collection({name:definition.name,type:'base',indexes:definition.indexes||[],listRule:null,viewRule:null,createRule:null,updateRule:null,deleteRule:null});for(const field of definition.fields)collection.fields.add(field);app.save(collection);}
}, () => {throw new Error('Identity schema rollback requires deliberate restore.');});
